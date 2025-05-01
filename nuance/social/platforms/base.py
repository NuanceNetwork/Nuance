# nuance/social/platforms/base.py
from abc import ABC, abstractmethod

class BasePlatform(ABC):
    """Base platform interface that all platforms must implement."""
    @abstractmethod
    async def get_user(self) -> dict:
        pass
    
    @abstractmethod
    async def get_post(self) -> dict:
        pass