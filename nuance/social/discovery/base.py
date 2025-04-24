from abc import ABC, abstractmethod
from typing import Generic, Optional, TypeVar

from nuance.social.platforms.base import BasePlatform
    

T = TypeVar("T", bound=BasePlatform)

class BaseDiscoveryStrategy(ABC, Generic[T]):
    """Base discovery strategy interface that all discovery strategies must implement."""
    def __init__(self, platform: Optional[T] = None):
        self.platform = platform
        
    @abstractmethod
    async def get_post(self, *args, **kwargs) -> dict:
        pass
    
    async def discover_new_posts(self, *args, **kwargs) -> list[dict]:
        pass
    
    @abstractmethod
    async def discover_new_interactions(self) -> list[dict]:
        pass
    
    @abstractmethod
    async def discover_new_contents(self) -> list[dict]:
        pass
    
    @abstractmethod
    async def verify_account(self, *args, **kwargs) -> bool:
        pass