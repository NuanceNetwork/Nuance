import asyncio
import shelve
from typing import cast
from types import SimpleNamespace

import bittensor as bt
from bittensor.core.chain_data.utils import decode_metadata
from loguru import logger


async def get_commitments(
    subtensor: bt.async_subtensor, metagraph: bt.metagraph, netuid: int
) -> dict[str, SimpleNamespace]:
    """
    Retrieve commitments for all miner hotkeys.
    """
    commits = await asyncio.gather(
        *[
            subtensor.substrate.query(
                module="Commitments",
                storage_function="CommitmentOf",
                params=[netuid, hotkey],
            )
            for hotkey in metagraph.hotkeys
        ]
    )
    result: dict[str, SimpleNamespace] = {}
    for uid, hotkey in enumerate(metagraph.hotkeys):
        commit = cast(dict, commits[uid])
        if commit:
            result[hotkey] = SimpleNamespace(
                uid=uid,
                hotkey=hotkey,
                block=commit["block"],
                account_id=decode_metadata(commit),
            )
            logger.debug(f"🔍 Found commitment for hotkey {hotkey}.")
    return result


async def wait_for_blocks(subtensor: bt.async_subtensor, last_block: int, block_interval: int, shutdown_event: asyncio.Event) -> int:
    """
    Wait until a given number of blocks have passed.
    """
    current_block = await subtensor.get_current_block()
    while (current_block - last_block) < block_interval and not shutdown_event.is_set():
        logger.info(f"⏳ Waiting... Current: {current_block}, Last: {last_block}")
        await subtensor.wait_for_block()
        current_block = await subtensor.get_current_block()
    return current_block

def update_weights(metagraph: bt.metagraph, step_block: int, db: shelve.Shelf) -> list[float]:
    """
    Calculate new miner weights using an exponential moving average.
    """
    weights = [0.0] * len(metagraph.hotkeys)
    for i, hotkey in enumerate(metagraph.hotkeys):
        if hotkey not in db["scores"]:
            continue
        block_numbers = sorted(db["scores"][hotkey].keys())
        if not block_numbers:
            continue
        ema = db["scores"][hotkey][block_numbers[0]]
        logger.debug(f"📊 {hotkey}: initial EMA from block {block_numbers[0]} = {ema}")
        for j in range(1, len(block_numbers)):
            current_block = block_numbers[j]
            prev_block = block_numbers[j - 1]
            block_diff = current_block - prev_block
            alpha = 2.0 / (block_diff + 1)
            current_value = db["scores"][hotkey][current_block]
            ema = (current_value * alpha) + (ema * (1 - alpha))
            logger.debug(
                f"📊 {hotkey}: updated EMA at block {current_block} = {ema:.2f} (alpha={alpha:.2f})"
            )
        weights[i] = max(0.0, ema)
        logger.info(f"🏁 Final weight for {hotkey}: {weights[i]:.4f}")
    total = sum(weights)
    if total > 0:
        weights = [w / total for w in weights]
    logger.info(f"🔢 Normalized weights: {weights}")
    return weights