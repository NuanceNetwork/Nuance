# nuance/utils/bittensor_utils.py
import asyncio
from typing import Callable, Awaitable

import bittensor as bt

import nuance.constants as cst
from nuance.utils.logging import logger
from nuance.settings import settings


class BittensorObjectsManager:
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(BittensorObjectsManager, cls).__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        self._wallet = None
        self._subtensor = None
        self._metagraph = None

    async def _get_wallet(self) -> bt.Wallet:
        if not self._wallet:
            logger.info("Setting up wallet...")
            self._wallet = bt.wallet(
                path=settings.WALLET_PATH,
                name=settings.WALLET_NAME,
                hotkey=settings.WALLET_HOTKEY,
            )
        return self._wallet
    
    async def _get_subtensor(self) -> bt.AsyncSubtensor:
        if not self._subtensor:
            logger.info("Setting up subtensor...")
            self._subtensor = bt.async_subtensor(
                network=settings.SUBTENSOR_NETWORK,
            )
            await self._subtensor.initialize()
        return self._subtensor
    
    async def _get_metagraph(self) -> bt.Metagraph:
        if not self._metagraph:
            logger.info("Setting up metagraph...")
            # Make sure we have subtensor initialized
            if not self._subtensor:
                await self._get_subtensor()
            self._metagraph = await self._subtensor.metagraph(settings.NETUID)
            # Once metagraph is initialized, periodically update it
            asyncio.create_task(self._periodic_update_metagraph())
        return self._metagraph
    
    async def _periodic_update_metagraph(self):
        while True:
            await asyncio.sleep(cst.EPOCH_LENGTH / 4)
            
            # Try up to 3 times
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    await self._metagraph.sync()
                    logger.info("🔍 Metagraph updated")
                    break  # Success, exit retry loop
                except Exception as e:
                    if attempt < max_retries - 1:  # Not the last attempt
                        logger.warning(f"⚠️ Metagraph update failed (attempt {attempt + 1}/{max_retries}): {e}")
                        # Optional: add a small delay between retries
                        await asyncio.sleep(1)
                    else:  # Last attempt failed
                        logger.exception("❌ Failed to update metagraph after 3 attempts")
            
bittensor_objects_manager = BittensorObjectsManager()

get_wallet: Callable[..., Awaitable[bt.Wallet]] = bittensor_objects_manager._get_wallet
get_subtensor: Callable[..., Awaitable[bt.AsyncSubtensor]] = bittensor_objects_manager._get_subtensor
get_metagraph: Callable[..., Awaitable[bt.Metagraph]] = bittensor_objects_manager._get_metagraph

async def get_axons() -> list[bt.AxonInfo]:
    metagraph = await get_metagraph()
    return metagraph.axons

async def is_validator(hotkey: str = None, uid: int = None) -> bool:
    metagraph = await get_metagraph()

    assert hotkey or uid, "Need to provide either hotkey or uid!"

    if hotkey:
        uid = metagraph.hotkeys.index(hotkey)

    return bool(metagraph.validator_permit[uid])
