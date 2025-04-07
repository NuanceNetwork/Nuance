import asyncio
import time
import traceback

import aiohttp
import bittensor as bt
from loguru import logger

import nuance.constants as constants
from nuance.settings import settings
from nuance.utils import http_request_with_retry

nuance_prompt_cache = {"nuance_prompt": {}, "last_updated": None}


async def get_nuance_prompt():
    current_time = time.time()
    if (
        nuance_prompt_cache["last_updated"] is None
        or current_time - nuance_prompt_cache["last_updated"]
        > constants.NUANCE_CONSTITUTION_UPDATE_INTERVAL
    ):
        # Update the cache if it's older than the update interval
        try:
            post_evaluation_prompt_url = (
                constants.NUANCE_CONSTITUTION_STORE_URL + "post_evaluation_prompt.txt"
            )
            bittensor_relevance_prompt_url = (
                constants.NUANCE_CONSTITUTION_STORE_URL
                + "topic_relevance_prompts/bittensor_prompt.txt"
            )

            async with aiohttp.ClientSession() as session:
                (
                    post_evaluation_prompt_data,
                    bittensor_relevance_prompt_data,
                ) = await asyncio.gather(
                    http_request_with_retry(session, "GET", post_evaluation_prompt_url),
                    http_request_with_retry(
                        session, "GET", bittensor_relevance_prompt_url
                    ),
                )

                post_evaluation_prompt = post_evaluation_prompt_data
                bittensor_relevance_prompt = bittensor_relevance_prompt_data

            nuance_prompt_cache["nuance_prompt"] = {
                "post_evaluation_prompt": post_evaluation_prompt,
                "bittensor_relevance_prompt": bittensor_relevance_prompt,
            }
            nuance_prompt_cache["last_updated"] = current_time
        except Exception as e:
            logger.error(f"Error fetching nuance prompt: {traceback.format_exc()}")

    return nuance_prompt_cache["nuance_prompt"]


async def model(
    prompt: str,
    model: str = "unsloth/Meta-Llama-3.1-8B-Instruct",
    max_tokens: int = 1024,
    temperature: float = 0.0,
    top_p: float = 0.5,
    keypair = None
) -> str:
    """
    Call the Chutes LLM API.
    """
    url = "https://api.nineteen.ai/v1/chat/completions"
    if settings.NINETEEN_API_KEY:
        # Use provided API key if provided
        headers = {
            "Authorization": f"Bearer {settings.NINETEEN_API_KEY}",
            "Content-Type": "application/json",
        }
    else:
        # Use authorization by validator 's signature
        nonce = str(time.time_ns())
        signature = f"0x{keypair.sign(nonce).hex()}"
        headers = {
            "validator-hotkey": keypair.ss58_address,
            "signature": signature,
            "nonce": nonce,
            "netuid": "23",
            "Content-Type": "application/json",
        }
        
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "top_p": top_p
    }
    async with aiohttp.ClientSession() as session:
        data = await http_request_with_retry(
            session, "POST", url, headers=headers, json=payload
        )
        logger.debug(f"🔍 Payload sent to LLM model: {payload}")
        logger.debug(f"🔍 Received response from LLM model: {data}")
        logger.info("✅ Received response from LLM model.")
        llm_response = data["choices"][0]["message"]["content"]
        logger.debug(f"🔍 LLM response: {llm_response}")
        return llm_response
