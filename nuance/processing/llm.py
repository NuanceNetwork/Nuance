# nuance/processing/llm.py
import asyncio
import re
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
        self.model_name = model_name or "unsloth/gemma-3-12b-it"
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
        keypair=None,
    ) -> str:
        """
        Call the LLM API.
        """
        url = "https://llm.chutes.ai/v1/chat/completions"

        headers = {
            "Authorization": f"Bearer {settings.CHUTES_API_KEY}",
            "Content-Type": "application/json",
        }

        messages = []
        if model == "unsloth/gemma-3-12b-it":
            # Use no-think mode for Qwen3
            messages.append({"role": "system", "content": "/no_think"})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": model,
            "messages": messages,
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
    keypair=None,  # Optional keypair parameter
) -> str:
    # Get wallet if not provided
    if not keypair:
        keypair = (await get_wallet()).hotkey

    service = await LLMService.get_instance()
    return await service.query(
        prompt=prompt,
        model=model,
        max_tokens=max_tokens,
        temperature=temperature,
        top_p=top_p,
        keypair=keypair,
    )


def strip_thinking(text: str) -> str:
    """
    Removes <think>...</think> sections from model output.
    """
    return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()


if __name__ == "__main__":
    print(asyncio.run(query_llm("Hello, world!")))
