# nuance/utils/networking.py
import asyncio

import aiohttp
from loguru import logger

MAX_RETRIES = 5
RETRY_DELAY = 5
HTTP_TIMEOUT = aiohttp.ClientTimeout(total=30)


async def async_http_request_with_retry(
    session: aiohttp.ClientSession, method: str, url: str, **kwargs
):
    """
    Make an HTTP request with retry logic.
    Returns JSON if response is application/json, otherwise returns text.
    """
    for attempt in range(MAX_RETRIES):
        try:
            async with session.request(
                method, url, timeout=HTTP_TIMEOUT, **kwargs
            ) as response:
                response.raise_for_status()
                content_type = response.headers.get("Content-Type", "").lower()
                if "application/json" in content_type:
                    return await response.json()
                return await response.text()
        except Exception as e:
            logger.warning(f"⚠️  Attempt {attempt + 1} for {url} failed: {e}")
            if attempt < MAX_RETRIES - 1:
                await asyncio.sleep(RETRY_DELAY * (attempt + 1))
            else:
                logger.error(f"❌ All {MAX_RETRIES} attempts failed for {url}")
                raise