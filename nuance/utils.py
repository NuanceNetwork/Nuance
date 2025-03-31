import asyncio
import aiohttp
import shelve
import time
import bittensor as bt
from loguru import logger

MAX_RETRIES = 3
RETRY_DELAY = 2
HTTP_TIMEOUT = aiohttp.ClientTimeout(total=10)

async def http_request_with_retry(
    session: aiohttp.ClientSession, method: str, url: str, **kwargs
):
    """
    Make an HTTP request with retry logic.
    """
    for attempt in range(MAX_RETRIES):
        try:
            async with session.request(
                method, url, timeout=HTTP_TIMEOUT, **kwargs
            ) as response:
                response.raise_for_status()
                return await response.json()
        except Exception as e:
            logger.warning(f"⚠️  Attempt {attempt + 1} for {url} failed: {e}")
            if attempt < MAX_RETRIES - 1:
                await asyncio.sleep(RETRY_DELAY * (attempt + 1))
            else:
                logger.error(f"❌ All {MAX_RETRIES} attempts failed for {url}.")
                raise
            
def verify_signature(ss58_address: str, signature: str, data: str) -> bool:
    """
    Verify a signature against an account id.
    """
    keypair = bt.Keypair(ss58_address=ss58_address)
    return keypair.verify(data=data, signature=signature)
            
# Database Helper: Record Errors
def record_db_error(db: shelve.Shelf, error_msg: str) -> None:
    """
    Record an error message into the shelve database.
    """
    db.setdefault("errors", [])
    db["errors"].append((time.time(), error_msg))
    logger.debug(f"💾 Recorded error: {error_msg}")