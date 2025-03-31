import aiohttp
from loguru import logger

from nuance.settings import settings
from nuance.utils import http_request_with_retry

async def model(
    prompt: str,
    model: str = "unsloth/Llama-3.2-3B-Instruct",
    max_tokens: int = 1024,
    temperature: float = 0.5,
) -> str:
    """
    Call the Chutes LLM API.
    """
    url = "https://api.nineteen.ai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {settings.NINETEEN_API_KEY}",
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
        logger.info("✅ Received response from LLM model.")
        return data["choices"][0]["message"]["content"]