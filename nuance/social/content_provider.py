# nuance/social/content_provider.py
from typing import Any, AsyncGenerator, Optional, TypedDict

import nuance.models as models
from nuance.social.discovery.base import BaseDiscoveryStrategy
from nuance.social.discovery.twitter import TwitterDiscoveryStrategy
from nuance.utils.logging import logger

class DiscoveredContent(TypedDict):
    posts: list[models.Post]
    interactions: list[models.Interaction]

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
    
    async def verify_account(
        self, 
        commit: models.Commit, 
        node: models.Node
    ) -> tuple[models.SocialAccount, Optional[str]]:
        """
        Verify an account from a commit. Return the social account if verified, otherwise return None and the error message.
        
        Args:
            commit: Commit data containing platform, account_id/username, verification_post_id, hotkey
            node: Node that is registering this account
            
        Returns:
            Tuple of (SocialAccount, error_message)
        """
        try:
            discovery = self._get_discovery(commit.platform)
            
            # Pass both username and account_id, let the strategy decide which to use
            account, error = await discovery.verify_account(
                username=commit.username,
                account_id=commit.account_id,
                verification_post_id=commit.verification_post_id,
                node=node,
            )
            return account, error
        except Exception as e:
            logger.error(f"Error verifying account: {str(e)}")
            return None, str(e)
        
    async def verifiy_post(
        self,
        post_id: str,
        platform: models.PlatformType,
        node: models.Node
    ) -> tuple[models.Post, Optional[str]]:
        """Verify a post on platform_type."""
        try:
            discovery = self._get_discovery(platform)

            post, error = await discovery.verify_post(
                post_id=post_id,
                node=node,
            )
            return post, error
        except Exception as e:
            logger.error(f"Error verifying post: {str(e)}")
            return None, str(e)


    async def discover_contents(self, social_account: models.SocialAccount) -> DiscoveredContent:
        """
        Discover new content (posts and interactions) for an account.
        
        Args:
            social_account: SocialAccount data containing platform and account_id
            
        Returns:
            Dictionary with "posts" and "interactions" keys
        """
        try:
            discovery = self._get_discovery(social_account.platform_type)
            contents = await discovery.discover_new_contents(social_account)
            
            return contents
        except Exception as e:
            logger.error(f"Error discovering content: {str(e)}")
            return DiscoveredContent(posts=[], interactions=[])
        
    async def discover_contents_streaming(self, social_account: models.SocialAccount) -> AsyncGenerator[models.Post | models.Interaction, None]:
        pass
    
    async def get_post(self, platform: str, post_id: str) -> Optional[models.Post]:
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
            return await discovery.get_post(post_id)
        except Exception as e:
            logger.error(f"Error getting post: {str(e)}")
            return None
        
    async def get_interaction(self, platform: str, interaction_id: str) -> Optional[models.Interaction]:
        """
        Get an interaction by ID.

        Args:
            platform: Platform name
            interaction_id: Interaction ID
            
        Returns:
            Interaction data or None if not found
        """
        try:
            discovery = self._get_discovery(platform)
            return await discovery.get_interaction(interaction_id)
        except Exception as e:
            logger.error(f"Error getting post: {str(e)}")
            return None