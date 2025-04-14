import asyncio
import datetime
import base58
import hashlib
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
            try:
                decoded_commit = decode_metadata(commit)
                account_id, verification_post_id = decoded_commit.split("@")
            except Exception as e:
                logger.error(f"❌ Error getting commitment for hotkey {hotkey}: {e}")
                continue
                
            result[hotkey] = SimpleNamespace(
                uid=uid,
                hotkey=hotkey,
                block=commit["block"],
                account_id=account_id,
                verification_post_id=verification_post_id,
            )
            logger.debug(f"🔍 Found commitment for hotkey {hotkey}.")
    return result


async def wait_for_blocks(
    subtensor: bt.async_subtensor,
    last_block: int,
    block_interval: int,
    shutdown_event: asyncio.Event,
) -> int:
    """
    Wait until a given number of blocks have passed.
    """
    current_block = await subtensor.get_current_block()
    while (current_block - last_block) < block_interval and not shutdown_event.is_set():
        logger.info(f"⏳ Waiting... Current: {current_block}, Last: {last_block}")
        await subtensor.wait_for_block()
        current_block = await subtensor.get_current_block()
    return current_block


def get_weights_by_scores(
    metagraph: bt.metagraph, step_block: int, db: shelve.Shelf
) -> list[float]:
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


def update_weights(
    metagraph: bt.metagraph, step_block: int, db: shelve.Shelf
) -> list[float]:
    """
    Calculate new miner weights by their scores and alpha burn ratio.
    """
    # Weights by scores
    scores_weights = get_weights_by_scores(metagraph, step_block, db)

    # Weight for owner's hotkey to do alpha burn
    alpha_burn_weights = [0.0] * len(metagraph.hotkeys)
    # Get the owner hotkey
    public_key_bytes = metagraph.owner_hotkey[0]
    # Convert to bytes
    public_key_bytes = bytes(public_key_bytes)
    # Prefix for Substrate address
    prefix = 42
    prefix_bytes = bytes([prefix])

    input_bytes = prefix_bytes + public_key_bytes

    # Calculate checksum (blake2b-512)
    blake2b = hashlib.blake2b(digest_size=64)
    blake2b.update(b"SS58PRE" + input_bytes)
    checksum = blake2b.digest()
    checksum_bytes = checksum[:2]  # Take first two bytes of checksum

    # Final bytes = prefix + public key + checksum
    final_bytes = input_bytes + checksum_bytes

    # Convert to base58
    owner_hotkey_base58 = base58.b58encode(final_bytes).decode()

    # Get the index of the owner hotkey
    owner_hotkey_index = metagraph.hotkeys.index(owner_hotkey_base58)
    logger.info(f"🔥 Burn alpha by setting weight for uid {owner_hotkey_index} - {owner_hotkey_base58} (owner's hotkey): 1")
    alpha_burn_weights[owner_hotkey_index] = 1

    # Combine weights
    # Alpha burn ratio is now 70% until next update
    alpha_burn_ratio = 0.7

    # Combine weights
    combined_weights = [
        (alpha_burn_ratio * alpha_burn_weight) + ((1 - alpha_burn_ratio) * score_weight)
        for alpha_burn_weight, score_weight in zip(alpha_burn_weights, scores_weights)
    ]

    return combined_weights
