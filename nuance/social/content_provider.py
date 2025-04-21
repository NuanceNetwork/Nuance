from types import SimpleNamespace
from typing import Any, Optional

from nuance.social.discovery.base import BaseDiscoveryStrategy
from nuance.social.discovery.twitter import TwitterDiscoveryStrategy
from nuance.utils.logging import logger


class SocialContentProvider:
    """
    Provider for social media content discovery and verification.
    
    Acts as a central access point for discovering and verifying
    content across multiple social platforms.
    """
    
    def __init__(self):
        """Initialize the social content provider."""
        # Initialize discovery strategies
        self.discovery_strategies = {
            "twitter": TwitterDiscoveryStrategy()
            # Add other platforms here as they're implemented
        }
    
    def _get_discovery(self, platform: str) -> BaseDiscoveryStrategy:
        """
        Get discovery strategy for a platform.
        
        Args:
            platform: Platform name
            
        Returns:
            Discovery strategy for the platform
            
        Raises:
            ValueError: If platform is not supported
        """
        if platform not in self.discovery_strategies:
            raise ValueError(f"Unsupported platform: {platform}")
        return self.discovery_strategies[platform]
    
    async def verify_account(self, commit: SimpleNamespace) -> tuple[bool, Optional[str]]:
        """
        Verify an account from a commit.
        
        Args:
            commit: Commit data containing platform, account_id, verification_post_id, hotkey
            
        Returns:
            Tuple of (success, error_message)
        """
        try:
            discovery = self._get_discovery(commit.platform)
            is_verified, error = await discovery.verify_account(
                commit.account_id, 
                commit.verification_post_id, 
                commit.hotkey
            )
            return is_verified, error
        except Exception as e:
            logger.error(f"Error verifying account: {str(e)}")
            return False, str(e)
    
    async def discover_content(self, commit: SimpleNamespace, since_id: Optional[str] = None) -> dict[str, list[dict[str, Any]]]:
        """
        Discover new content (posts and interactions) for an account.
        
        Args:
            commit: Commit data containing platform and account_id
            since_id: Optional ID to fetch content newer than this
            
        Returns:
            Dictionary with "posts" and "interactions" keys
        """
        try:
            discovery = self._get_discovery(commit.platform)
            contents = await discovery.discover_new_contents(commit.account_id, since_id)
            
            # Tag all content with the miner's hotkey for tracking
            for post in contents.get("posts", []):
                post["miner_hotkey"] = commit.hotkey
                
            for interaction in contents.get("interactions", []):
                interaction["miner_hotkey"] = commit.hotkey
            
            return contents
        except Exception as e:
            logger.error(f"Error discovering content: {str(e)}")
            return {"posts": [], "interactions": []}
    
    async def get_post(self, platform: str, post_id: str) -> Optional[dict[str, Any]]:
        """
        Get a post by ID.
        
        Args:
            platform: Platform name
            post_id: Post ID
            
        Returns:
            Post data or None if not found
        """
        try:
            discovery = self._get_discovery(platform)
            platform_api = discovery.platform
            return await platform_api.get_post(post_id)
        except Exception as e:
            logger.error(f"Error getting post: {str(e)}")
            return None