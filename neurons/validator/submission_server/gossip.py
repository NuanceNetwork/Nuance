# neurons/validator/submission_server/gossip.py
import asyncio
from datetime import datetime, timedelta

import aiohttp
import bittensor as bt

from nuance.utils.logging import logger
from nuance.utils.bittensor_utils import get_wallet, get_metagraph, get_axons
from nuance.utils.epistula import create_request

from .models import GossipData


class GossipHandler:
    """
    Handles gossip between validators.
    
    Prevents loops by tracking UUIDs and forwards submissions
    to other validators for redundancy.
    """
    
    def __init__(
        self,
        uuid_ttl_hours: int = 24,
        gossip_timeout: int = 5
    ):
        self.uuid_ttl_hours = uuid_ttl_hours
        self.gossip_timeout = gossip_timeout
        
        # Track seen UUIDs with timestamps
        self.seen_uuids: dict[str, datetime] = {}
        self._lock = asyncio.Lock()
        
        # Track gossip statistics
        self.gossip_stats = {
            "total_sent": 0,
            "total_success": 0,
            "total_failed": 0
        }
    
    def has_seen_uuid(self, uuid: str) -> bool:
        """Check if UUID has been seen (thread-safe)"""
        return uuid in self.seen_uuids
    
    async def mark_uuid_seen(self, uuid: str):
        """Mark UUID as seen with current timestamp"""
        async with self._lock:
            self.seen_uuids[uuid] = datetime.now()
    
    async def get_validator_axons(self) -> list[bt.AxonInfo]:
        """
        Get list of validator axons from metagraph.
        
        Returns:
            List of AxonInfo for validators
        """
        validator_axons = []
        metagraph = await get_metagraph()
        self_hotkey = (await get_wallet()).hotkey.ss58_address
        all_axons = await get_axons()

        for axon in all_axons:
            hotkey = axon.hotkey
            if hotkey not in metagraph.hotkeys:
                continue

            # Skip self
            if hotkey == self_hotkey:
                continue

            uid = metagraph.hotkeys.index(hotkey)
            
            # Check if validator permitted
            if metagraph.validator_permit[uid]:
                # Skip if no IP
                if not axon.ip or axon.ip == "0.0.0.0":
                    logger.debug(f"Skipping axon with invalid IP: {axon}")
                    continue

                validator_axons.append(axon)
        
        return validator_axons
    
    async def broadcast_submission(
        self, 
        original_body: bytes,
        original_body_model: str, 
        original_headers: dict[str, str]
    ):
        """
        Broadcast submission to all other validators.
        
        Args:
            original_body: Original request body as bytes
            original_headers: Original Epistula headers
        """
        validator_axons = await self.get_validator_axons()
        
        if not validator_axons:
            logger.info("No other validators to gossip to")
            return
        
        logger.info(f"Broadcasting to {len(validator_axons)} validators")
        
        # Prepare gossip data
        gossip_data = GossipData(
            original_body_hex=original_body.hex(),
            original_body_model=original_body_model,
            original_headers=original_headers
        ).model_dump()
        
        # Send to all validators concurrently
        tasks = []
        async with aiohttp.ClientSession() as session:
            for axon in validator_axons:
                url = f"http://{axon.ip}:{axon.port}/gossip"
                task = self._send_gossip(session, url, gossip_data, axon.hotkey)
                tasks.append((axon.hotkey, task))
            
            # Wait for all to complete
            results = []
            for hotkey, task in tasks:
                try:
                    success = await task
                    results.append((hotkey, success))
                except Exception as e:
                    logger.debug(f"Gossip to {hotkey} failed with exception: {e}")
                    results.append((hotkey, False))
        
        # Update statistics
        successes = sum(1 for _, success in results if success)
        self.gossip_stats["total_sent"] += len(validator_axons)
        self.gossip_stats["total_success"] += successes
        self.gossip_stats["total_failed"] += (len(validator_axons) - successes)
        
        # Log results
        logger.info(f"Gossip broadcast: {successes}/{len(validator_axons)} successful")
        
        # Log failures for debugging
        for hotkey, success in results:
            if not success:
                logger.debug(f"Failed to gossip to {hotkey}")
    
    async def _send_gossip(
        self,
        session: aiohttp.ClientSession,
        url: str,
        gossip_data: dict,
        receiver_hotkey: str
    ) -> bool:
        """
        Send gossip to a single validator.
        
        Returns:
            True if successful, False otherwise
        """
        try:
            # Create signed request with Epistula V2
            body_bytes, headers = create_request(
                data=gossip_data,
                sender_keypair=(await get_wallet()).hotkey,
                receiver_hotkey=receiver_hotkey
            )
            
            # Send request
            async with session.post(
                url,
                data=body_bytes,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=self.gossip_timeout)
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    status = data.get("status", "unknown")
                    
                    # Log if already processed (normal behavior)
                    if status == "already_processed":
                        logger.debug(f"Gossip to {url}: already processed")
                    
                    return True
                else:
                    text = await response.text()
                    logger.debug(f"Gossip to {url} failed: HTTP {response.status} - {text}")
                    return False
                    
        except asyncio.TimeoutError:
            logger.debug(f"Gossip to {url} timed out")
            return False
        except aiohttp.ClientError as e:
            logger.debug(f"Gossip to {url} connection error: {e}")
            return False
        except Exception as e:
            logger.debug(f"Gossip to {url} unexpected error: {e}")
            return False
    
    async def periodic_cleanup(self):
        """Clean old UUIDs periodically to prevent memory growth"""
        while True:
            try:
                # Run cleanup every hour
                await asyncio.sleep(3600)
                await self._cleanup_old_uuids()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in gossip cleanup: {e}")
    
    async def _cleanup_old_uuids(self):
        """Remove UUIDs older than TTL"""
        async with self._lock:
            now = datetime.now()
            cutoff = now - timedelta(hours=self.uuid_ttl_hours)
            
            # Find old UUIDs
            old_uuids = [
                uuid for uuid, timestamp in self.seen_uuids.items()
                if timestamp < cutoff
            ]
            
            # Remove them
            for uuid in old_uuids:
                del self.seen_uuids[uuid]
            
            if old_uuids:
                logger.info(
                    f"Gossip cleanup: removed {len(old_uuids)} old UUIDs, "
                    f"{len(self.seen_uuids)} remaining"
                )
                
            # Log statistics
            logger.info(
                f"Gossip stats - Total: {self.gossip_stats['total_sent']}, "
                f"Success: {self.gossip_stats['total_success']}, "
                f"Failed: {self.gossip_stats['total_failed']}"
            )
    
    def get_stats(self) -> dict:
        """Get gossip statistics"""
        return {
            "seen_uuids": len(self.seen_uuids),
            "gossip_stats": self.gossip_stats.copy()
        }