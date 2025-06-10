# neurons/validator/submission_server/app.py
import asyncio
import json
import time
from contextlib import asynccontextmanager
from typing import Annotated

import bittensor as bt
from fastapi import BackgroundTasks, Depends, FastAPI
from pydantic import BaseModel

from nuance.utils.bittensor_utils import get_metagraph, get_wallet, is_validator
from nuance.utils.epistula import verify_request
from nuance.utils.logging import logger

from .dependencies import create_verified_dependency, create_gossip_verified_dependency
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
        uuid = headers.get("Epistula-Uuid")
        sender_hotkey = headers.get("Epistula-Signed-By")
        sender_uid = metagraph.hotkeys.index(sender_hotkey)

        # Now the code is much cleaner!
        if gossip_handler.has_seen_uuid(uuid):
            return {"status": "already_processed"}

        # Check rate limit
        alpha_stake = metagraph.alpha_stake[sender_uid]
        if not is_validator(sender_hotkey, metagraph):
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
        original_body = submission_data.model_dump_json().encode()
        background_tasks.add_task(
            gossip_handler.broadcast_submission,
            original_body,
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
        uuid = headers.get("Epistula-Uuid")
        sender_hotkey = headers.get("Epistula-Signed-By")

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
            "hotkey": hotkey,
            "alpha_stake": alpha_stake,
            "is_validator": is_validator(hotkey, metagraph),
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
                "hotkey": sender_hotkey,
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
