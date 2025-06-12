# nuance/utils/bittensor_utils.py
import asyncio
from typing import Callable, Awaitable, Optional, TYPE_CHECKING

import bittensor as bt
from bittensor.utils import unlock_key, Certificate
from bittensor.utils.networking import get_external_ip
from bittensor.core.extrinsics.asyncex.serving import serve_extrinsic

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


async def serve_axon_extrinsic(
    subtensor: bt.AsyncSubtensor,
    wallet: bt.Wallet,
    netuid: int,
    external_port: int,
    external_ip: Optional[str] = None,
    wait_for_inclusion: bool = False,
    wait_for_finalization: bool = True,
    certificate: Optional[Certificate] = None,
):
    """Serves the axon to the network.

    Args:
        subtensor (bittensor.core.async_subtensor.AsyncSubtensor): Subtensor instance object.
        netuid (int): The ``netuid`` being served on.
        external_port (int): External port for the axon
        wait_for_inclusion (bool): If set, waits for the extrinsic to enter a block before returning ``True``, or
            returns ``False`` if the extrinsic fails to enter the block within the timeout.
        wait_for_finalization (bool): If set, waits for the extrinsic to be finalized on the chain before returning
            ``True``, or returns ``False`` if the extrinsic fails to be finalized within the timeout.
        certificate (bittensor.utils.Certificate): Certificate to use for TLS. If ``None``, no TLS will be used.
            Defaults to ``None``.

    Returns:
        success (bool): Flag is ``True`` if extrinsic was finalized or included in the block. If we did not wait for
            finalization / inclusion, the response is ``True``.
    """
    if not (unlock := unlock_key(wallet, "hotkey")).success:
        logger.error(unlock.message)
        return False

    # ---- Get external ip ----
    if not external_ip or external_ip == "0.0.0.0":
        try:
            external_ip = await asyncio.get_running_loop().run_in_executor(
                None, get_external_ip
            )
            logger.success(
                f":white_heavy_check_mark: [green]Found external ip:[/green] [blue]{external_ip}[/blue]"
            )
        except Exception as e:
            raise ConnectionError(
                f"Unable to attain your external ip. Check your internet connection. error: {e}"
            ) from e

    # ---- Subscribe to chain ----
    serve_success = await serve_extrinsic(
        subtensor=subtensor,
        wallet=wallet,
        ip=external_ip,
        port=external_port,
        protocol=4,
        netuid=netuid,
        wait_for_inclusion=wait_for_inclusion,
        wait_for_finalization=wait_for_finalization,
        certificate=certificate,
    )
    return serve_success


async def is_validator(hotkey: str = None, uid: int = None) -> bool:
    metagraph = await get_metagraph()

    assert hotkey or uid, "Need to provide either hotkey or uid!"

    if hotkey:
        uid = metagraph.hotkeys.index(hotkey)

    return bool(metagraph.validator_permit[uid])
