# neurons/validator/submission_server/app.py
import asyncio
import json
import time
from contextlib import asynccontextmanager
from typing import Annotated

import aiohttp
import bittensor as bt
from fastapi import BackgroundTasks, Body, Depends, FastAPI, HTTPException, Request
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from nuance.models import PlatformType
from nuance.utils.bittensor_utils import (
    get_axons,
    get_metagraph,
    get_subtensor,
    get_wallet,
    is_validator,
)
from nuance.utils.epistula import create_request
from nuance.utils.logging import logger

from .dependencies import create_gossip_verified_dependency, create_verified_dependency
from .gossip import GossipHandler
from .models import SubmissionData
from .rate_limiter import RateLimiter


def create_submission_app(
    submission_queue: asyncio.Queue,
) -> FastAPI:
    """
    Create FastAPI app for content submission.

    Args:
        submission_queue: Queue to push valid submissions to

    Returns:
        FastAPI application instance
    """

    # Initialize components
    rate_limiter = RateLimiter()
    gossip_handler = GossipHandler()
    # Register rate limiter
    limiter = Limiter(key_func=get_remote_address)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        """Manage app lifecycle"""
        # Start background tasks
        cleanup_task = asyncio.create_task(rate_limiter.periodic_cleanup())
        gossip_cleanup_task = asyncio.create_task(gossip_handler.periodic_cleanup())

        logger.info("Submission server started!")

        yield

        # Shutdown
        cleanup_task.cancel()
        gossip_cleanup_task.cancel()

        try:
            await cleanup_task
            await gossip_cleanup_task
        except asyncio.CancelledError:
            pass

        logger.info("Submission server shutdown complete@")

    # Create app
    app = FastAPI(title="Nuance Submission Server", lifespan=lifespan)
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    @app.post("/submit_through_node")
    @limiter.limit("1 / 10 minutes")
    async def submit_through_node(
        request: Request,
        submission_data: SubmissionData, 
    ):
        metagraph: bt.Metagraph = await get_metagraph()
        wallet = await get_wallet()
        all_axons = await get_axons()
        all_validator_axons = []
        for axon in all_axons:
            axon_hotkey = axon.hotkey
            if axon_hotkey not in metagraph.hotkeys:
                continue
            axon_uid = metagraph.hotkeys.index(axon_hotkey)
            if metagraph.validator_permit[axon_uid] and axon.ip != "0.0.0.0":
                all_validator_axons.append(axon)

        # Inner method to send request to a single axon
        async def send_request_to_axon(axon: bt.AxonInfo):
            url = f"http://{axon.ip}:{axon.port}/submit"  # Update with the correct URL endpoint
            request_body_bytes, request_headers = create_request(
                data=submission_data.model_dump(),
                sender_keypair=wallet.hotkey,
                receiver_hotkey=axon.hotkey
            )

            try:
                async with aiohttp.ClientSession() as session:
                    async with session.post(url, json=submission_data.model_dump(), headers=request_headers) as response:
                        if response.status == 200:
                            return {'axon': axon.hotkey, 'status': response.status, 'response': await response.json()}
                        else:
                            error_message = await response.text()  # Capture response message for error details
                            return {'axon': axon.hotkey, 'status': response.status, 'error': error_message}
            except Exception as e:
                return {'axon': axon.hotkey, 'status': 'error', 'error': str(e)}

        # Send requests concurrently
        tasks = [send_request_to_axon(axon) for axon in all_validator_axons]
        logger.info(f"Submitting to {len(tasks)} validators")
        responses = await asyncio.gather(*tasks, return_exceptions=True)

        responses = []
        for response in responses:
            responses.append(response)
            if isinstance(response, Exception):
                logger.error(f"Exception occurred: {response}")
            else:
                if "error" in response:
                    logger.error(f"Error while sending to axon {response['axon']}: {response['error']}")
                else:
                    logger.info(f"Successfully submitted to axon {response['axon']} with status {response['status']}")

        return "\n".join(responses)

    @app.post("/submit")
    async def submit_content(
        verified_submission: Annotated[
            tuple[SubmissionData, dict],
            Depends(create_verified_dependency(data_model=SubmissionData)),
        ],
        metagraph: Annotated[bt.Metagraph, Depends(get_metagraph)],
        background_tasks: BackgroundTasks,
    ):
        submission_data, headers = verified_submission
        uuid = headers.get("Epistula-Uuid") or headers.get("Epistula-Uuid".lower())
        sender_hotkey = headers.get("Epistula-Signed-By") or headers.get("Epistula-Signed-By".lower())
        sender_uid = metagraph.hotkeys.index(sender_hotkey)

        if gossip_handler.has_seen_uuid(uuid):
            return {"status": "already_processed"}

        # Check rate limit
        alpha_stake = metagraph.alpha_stake[sender_uid]
        if not await is_validator(sender_hotkey, metagraph):
            allowed, message, _ = await rate_limiter.check_and_update(
                sender_hotkey, alpha_stake
            )
            if not allowed:
                return {"status": "rate_limited", "message": message}

        # Mark UUID as seen
        await gossip_handler.mark_uuid_seen(uuid)

        # Queue submission
        background_tasks.add_task(
            queue_submission,
            submission_data,
            sender_hotkey,
            uuid,
            submission_queue,
            from_gossip=False,
        )

        # Gossip to other validators in background
        original_body = submission_data.model_dump()
        original_body_bytes = json.dumps(original_body).encode()
        background_tasks.add_task(
            gossip_handler.broadcast_submission,
            original_body_bytes,
            "SubmissionData",
            headers,
        )

        return {"status": "accepted", "message": "Submission queued for processing"}

    @app.post("/gossip")
    async def receive_gossip(
        verified_submission: Annotated[
            tuple[SubmissionData, dict], Depends(create_gossip_verified_dependency())
        ],
        background_tasks: BackgroundTasks,
    ):
        """
        Receive gossip from other validators.

        Only accepts requests from validators with sufficient stake.
        """
        submission_data, headers = verified_submission
        uuid = headers.get("Epistula-Uuid".lower())
        sender_hotkey = headers.get("Epistula-Signed-By".lower())
        
        if not uuid:
            logger.warning("Gossip missing UUID")
            return {"status": "invalid"}

        if gossip_handler.has_seen_uuid(uuid):
            return {"status": "already_processed"}

        await gossip_handler.mark_uuid_seen(uuid)

        # Optional: validate expected type if required
        if not isinstance(submission_data, SubmissionData):
            logger.warning("Received unsupported submission type")
            return {"status": "invalid_model"}

        # Queue submission
        background_tasks.add_task(
            queue_submission,
            submission_data,
            sender_hotkey,
            uuid,
            submission_queue,
            from_gossip=True,
        )

        return {"status": "received"}

    @app.get("/health")
    async def health():
        """Health check endpoint"""
        return {
            "status": "healthy",
            "validator": (await get_wallet()).hotkey.ss58_address,
            "queue_size": submission_queue.qsize(),
            "rate_limiter_entries": len(rate_limiter.submissions),
            "seen_uuids": len(gossip_handler.seen_uuids),
        }

    @app.get("/rate_limit/{hotkey}")
    async def check_rate_limit(
        hotkey: str,
        metagraph: Annotated[bt.Metagraph, Depends(get_metagraph)],
    ):
        """Check rate limit status for a miner"""
        if hotkey not in metagraph.hotkeys:
            return {
                "hotkey": hotkey,
                "alpha_stake": None,
                "is_validator": None,
                "usage": None,
            }

        uid = metagraph.hotkeys.index(hotkey)
        alpha_stake = metagraph.alpha_stake[uid]
        usage = await rate_limiter.get_usage(hotkey, alpha_stake)

        return {
            "hotkey": str(hotkey),
            "alpha_stake": float(alpha_stake),
            "is_validator": bool(await is_validator(hotkey, metagraph)),
            "usage": usage,
        }

    return app


async def queue_submission(
    submission_data: SubmissionData,
    sender_hotkey: str,
    uuid: str,
    submission_queue: asyncio.Queue,
    from_gossip: bool = False,
):
    """Queue submission for processing."""
    try:
        await submission_queue.put(
            {
                "hotkey": submission_data.node_hotkey or sender_hotkey,
                "platform": submission_data.platform.value,
                "account_id": submission_data.account_id,
                "verification_post_id": submission_data.verification_post_id,
                "post_id": submission_data.post_id,
                "interaction_id": submission_data.interaction_id,
                "uuid": uuid,
                "received_at": int(time.time()),
                "from_gossip": from_gossip,
            }
        )

        source = "gossip" if from_gossip else "direct"
        logger.info(
            f"Queued {source} submission from {sender_hotkey} "
            f"(post: {submission_data.post_id or 'none'}, "
            f"interaction: {submission_data.interaction_id or 'none'})"
        )
    except Exception as e:
        logger.error(f"Error queueing submission from {sender_hotkey}: {e}")
