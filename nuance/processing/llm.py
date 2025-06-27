# nuance/processing/llm.py
import asyncio
import time
from typing import ClassVar, Optional

import aiohttp
from loguru import logger

from nuance.utils.bittensor_utils import get_wallet
from nuance.utils.networking import async_http_request_with_retry
from nuance.settings import settings


class LLMService:
    """
    Singleton service for handling LLM requests.
    Focuses solely on LLM interaction.
    """

    _instance: ClassVar[Optional["LLMService"]] = None
    _lock = asyncio.Lock()

    def __new__(cls, *args, **kwargs):
        return cls.get_instance(*args, **kwargs)

    @classmethod
    async def get_instance(cls, *args, **kwargs) -> "LLMService":
        """Get or create the singleton instance asynchronously."""
        async with cls._lock:
            if cls._instance is None:
                instance = super().__new__(cls)
                await instance._initialize(*args, **kwargs)
                cls._instance = instance
            return cls._instance

    async def _initialize(self, model_name: Optional[str] = None):
        """Initialize the LLM service."""
        self.model_name = model_name or "Qwen/Qwen2.5-7B-Instruct"
        logger.info(f"LLM Service initialized with model: {self.model_name}")

    async def query(
        self,
        prompt: str,
        model: Optional[str] = None,
        max_tokens: int = 1024,
        temperature: float = 0.0,
        top_p: float = 0.5,
        keypair=None,
    ) -> str:
        """
        Send a query to the LLM.

        Args:
            prompt: The prompt text
            model: Optional model override
            max_tokens: Maximum tokens to generate
            temperature: Temperature parameter (0.0-1.0)
            top_p: Top-p sampling parameter
            keypair: Optional keypair for authentication

        Returns:
            Generated response text
        """
        # Use the provided model function
        return await self._call_model(
            prompt=prompt,
            model=model or self.model_name,
            max_tokens=max_tokens,
            temperature=temperature,
            top_p=top_p,
            keypair=keypair,
        )

    async def _call_model(
        self,
        prompt: str,
        model: str,
        max_tokens: int,
        temperature: float,
        top_p: float,
        keypair=None
    ) -> str:
        """
        Call the LLM API.
        """
        url = "https://api.nineteen.ai/v1/chat/completions"
        
        # if settings.NINETEEN_API_KEY:
        #     print(f"Using provided API key: {settings.NINETEEN_API_KEY}")
        #     # Use provided API key if provided
        #     headers = {
        #         "Authorization": f"Bearer {settings.NINETEEN_API_KEY}",
        #         "Content-Type": "application/json",
        #     }
        # else:

        # Use authorization by validator's signature
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
            "top_p": top_p,
        }
        async with aiohttp.ClientSession() as session:
            data = await async_http_request_with_retry(
                session, "POST", url, headers=headers, json=payload
            )
            logger.debug(f"🔍 Payload sent to LLM model: {payload}")
            logger.debug(f"🔍 Received response from LLM model: {data}")
            logger.info("✅ Received response from LLM model.")
            llm_response = data["choices"][0]["message"]["content"]
            logger.debug(f"🔍 LLM response: {llm_response}")
            return llm_response


# Convenience function for global access
async def query_llm(
    prompt: str,
    model: Optional[str] = None,
    max_tokens: int = 1024,
    temperature: float = 0.0,
    top_p: float = 0.5,
    keypair=None  # Optional keypair parameter
) -> str:
    # Get wallet if not provided
    if not keypair and not settings.NINETEEN_API_KEY:
        keypair = (await get_wallet()).hotkey
    
    service = await LLMService.get_instance()
    return await service.query(
        prompt=prompt,
        model=model,
        max_tokens=max_tokens,
        temperature=temperature,
        top_p=top_p,
        keypair=keypair
    )
    
if __name__ == "__main__":
    print(asyncio.run(query_llm("Hello, world!")))
