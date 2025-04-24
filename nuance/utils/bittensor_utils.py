import os
import asyncio
from typing import Callable, Awaitable
import bittensor as bt
from nuance.utils.logging import logger

import nuance.constants as constants
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
    
    async def _get_subtensor(self) -> bt.Subtensor:
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
            await asyncio.sleep(constants.EPOCH_LENGTH)
            await self._metagraph.sync()
            
bittensor_objects_manager = BittensorObjectsManager()

get_wallet: Callable[..., Awaitable[bt.Wallet]] = bittensor_objects_manager._get_wallet
get_subtensor: Callable[..., Awaitable[bt.Subtensor]] = bittensor_objects_manager._get_subtensor
get_metagraph: Callable[..., Awaitable[bt.Metagraph]] = bittensor_objects_manager._get_metagraph
