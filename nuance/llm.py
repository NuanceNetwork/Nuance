import aiohttp
import bittensor as bt

from nuance.settings import settings
from nuance.utils import http_request_with_retry

async def model(
    prompt: str,
    model: str = "unsloth/gemma-3-4b-it",
    max_tokens: int = 1024,
    temperature: float = 0.7,
) -> str:
    """
    Call the Chutes LLM API.
    """
    url = "https://llm.chutes.ai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {settings.CHUTES_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    async with aiohttp.ClientSession() as session:
        data = await http_request_with_retry(
            session, "POST", url, headers=headers, json=payload
        )
        bt.logging.info("✅ Received response from LLM model.")
        return data["choices"][0]["message"]["content"]