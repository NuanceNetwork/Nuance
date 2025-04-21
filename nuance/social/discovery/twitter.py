# nuance/social/discovery/twitter.py
import asyncio
import csv
import datetime
import time
from typing import Optional
import traceback

import aiohttp

import nuance.constants as constants
import nuance.models as models
from nuance.utils.logging import logger
from nuance.utils.networking import async_http_request_with_retry
from nuance.social.discovery.base import BaseDiscoveryStrategy
from nuance.social.platforms.twitter import TwitterPlatform


class TwitterDiscoveryStrategy(BaseDiscoveryStrategy[TwitterPlatform]):
    def __init__(self, platform: Optional[TwitterPlatform] = None):
        if platform is None:
            platform = TwitterPlatform()

        super().__init__(platform)

        self._verified_users_cache: dict[str, bool] = {
            "verified_user_ids": set(),
            "last_updated": None,
        }
        self._cache_lock = asyncio.Lock()

    async def discover_new_posts(self, username: str) -> list[dict]:
        try:
            return await self.platform.get_all_posts(username)
        except Exception as e:
            logger.error(
                f"❌ Error discovering new posts for {username}: {traceback.format_exc()}"
            )
            return []

    async def discover_new_interactions(self, username: str) -> list[models.Interaction]:
        """
        Discover new interactions for a Twitter account. This method currently only discovers replies.
        """
        replies = await self.platform.get_all_replies(username)
        # Standardize the replies
        standardized_replies = [_reply_tweet_to_interaction(reply) for reply in replies]
        return standardized_replies

    async def get_verified_users(self) -> set[str]:
        """
        Get a set of verified Twitter user IDs.
        Maintains a cache that refreshes periodically.

        Returns:
            Set of verified user IDs
        """
        current_time = time.time()

        # Check if update is needed without acquiring the lock
        if (
            self._verified_users_cache["last_updated"] is None
            or current_time - self._verified_users_cache["last_updated"]
            > constants.NUANCE_CONSTITUTION_UPDATE_INTERVAL
        ):
            # Only acquire the lock if update might be needed
            async with self._cache_lock:
                # Re-check after acquiring the lock (another task might have updated meanwhile)
                if (
                    self._verified_users_cache["last_updated"] is None
                    or current_time - self._verified_users_cache["last_updated"]
                    > constants.NUANCE_CONSTITUTION_UPDATE_INTERVAL
                ):
                    try:
                        twitter_verified_users_url = (
                            constants.NUANCE_CONSTITUTION_STORE_URL
                            + "/verified_users/twitter_verified_users.csv"
                        )

                        async with aiohttp.ClientSession() as session:
                            twitter_verified_users_data = (
                                await async_http_request_with_retry(
                                    session, "GET", twitter_verified_users_url
                                )
                            )

                        # Process the CSV data
                        lines = twitter_verified_users_data.splitlines()
                        reader = csv.DictReader(lines)
                        self._verified_users_cache["verified_user_ids"] = {
                            row["id"] for row in reader if "id" in row
                        }

                        logger.debug(
                            f"✅ Fetched verified Twitter users: {str(self._verified_users_cache['verified_user_ids'])[:100]} ..."
                        )
                        self._verified_users_cache["last_updated"] = current_time
                    except Exception as e:
                        logger.error(
                            f"❌ Error fetching verified Twitter users: {traceback.format_exc()}"
                        )

        return self._verified_users_cache["verified_user_ids"]

    async def discover_new_contents(self, username: str) -> dict[str, list[dict]]:
        """
        Discover new content (posts and interactions) for a Twitter account.

        Args:
            account_id: Twitter username
            since_id: Optional ID to fetch content newer than this

        Returns:
            Dictionary with "posts" and "interactions" keys
        """
        try:
            # Get new interactions to the account, currently only replies
            all_replies = await self.discover_new_interactions(username)

            # Filter replies
            verified_replies = []
            for reply in all_replies:
                reply_id = reply.platform_id
                # 1.1 Check if the reply comes from a verified username using the CSV list using user id.
                verified_user_ids = await self.get_verified_users()
                if reply.account_id not in verified_user_ids:
                    logger.info(
                        f"🚫 Reply {reply_id} from unverified account with id {reply.account_id}; skipping."
                    )
                    continue

                # 1.2 Check if the reply comes from an account younger than 1 year.
                account_created_at = datetime.datetime.strptime(
                    reply["user"]["created_at"], "%a %b %d %H:%M:%S %z %Y"
                )
                account_age = (
                    datetime.datetime.now(datetime.timezone.utc) - account_created_at
                )
                if account_age.days < 365:
                    logger.info(
                        f"⏳ Reply {reply_id} from account younger than 1 year; skipping."
                    )
                    continue
                verified_replies.append(reply)
            # Get parent posts of the replies, these are considered as new posts
            all_parent_post_ids = [
                reply.post_id
                for reply in all_replies
                if reply.post_id is not None
            ]

            posts = await asyncio.gather(
                *[self.platform.get_post(post_id) for post_id in all_parent_post_ids]
            )

            return {"posts": posts, "interactions": verified_replies}

        except Exception as e:
            logger.error(
                f"❌ Error discovering new contents for {username}: {traceback.format_exc()}"
            )
            return {"posts": [], "interactions": []}

    async def verify_account(
        self, username: str, verification_post_id: str, hotkey: str
    ) -> bool:
        try:
            verification_post = await self.platform.get_post(verification_post_id)
            # Check if username is correct
            assert verification_post["user"]["username"] == username
            # Check if miner 's hotkey is in the post text
            assert hotkey in verification_post["text"]
            # Check if the post quotes the Nuance announcement post
            assert verification_post["is_quote_tweet"]
            assert (
                verification_post["quoted_status_id"]
                == constants.NUANCE_ANNOUNCEMENT_POST_ID
            )
            return True
        except Exception as e:
            logger.error(
                f"❌ Error verifying account {username} from hotkey {hotkey}: {traceback.format_exc()}"
            )
            return False


# Helper methods
def _twitter_user_to_social_account(
    user: dict, node: models.Node = None
) -> models.SocialAccount:
    """
    Convert a Twitter user dictionary to a SocialAccount object.
    Args:
        user: Twitter user dictionary
        node: Optional Node object that registered the account
    Returns:
        SocialAccount object
    """
    return models.SocialAccount(
        platform_type=models.PlatformType.TWITTER,
        account_id=user.get("id"),
        username=user.get("username"),
        node_hotkey=node.hotkey if node else None,
        node_netuid=node.netuid if node else None,
    )


def _tweet_to_post(tweet: dict) -> models.Post:
    """
    Convert a Twitter tweet dictionary to a Post object.
    """
    return models.Post(
        id=tweet.get("id"),
        platform_id=tweet.get("id"),
        platform_type=models.PlatformType.TWITTER,
        content=tweet.get("text"),
        account_id=tweet.get("user", {}).get("id"),
        extra_data=tweet,
    )


def _reply_tweet_to_interaction(tweet: dict) -> models.Interaction:
    """
    Convert a Twitter tweet dictionary to an Interaction object.
    """
    return models.Interaction(
        id=tweet.get("id"),
        platform_id=tweet.get("id"),
        platform_type=models.PlatformType.TWITTER,
        interaction_type=models.InteractionType.REPLY,
        post_id=tweet.get("in_reply_to_status_id"),
        content=tweet.get("text"),
        account_id=tweet.get("user", {}).get("id"),
        extra_data=tweet,
    )
