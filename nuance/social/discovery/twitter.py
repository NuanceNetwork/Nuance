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
        
    async def get_post(self, post_id: str) -> models.Post:
        raw_post = await self.platform.get_post(post_id)
        return _tweet_to_post(raw_post, social_account=raw_post.get("user"))

    async def discover_new_posts(self, username: str) -> list[models.Post]:
        try:
            raw_posts = await self.platform.get_all_posts(username)
            return [_tweet_to_post(post, social_account=post.get("user")) for post in raw_posts]
        except Exception as e:
            logger.error(
                f"❌ Error discovering new posts for {username}: {traceback.format_exc()}"
            )
            return []

    async def discover_new_interactions(
        self, username: str
    ) -> list[models.Interaction]:
        """
        Discover new interactions for a Twitter account. This method currently only discovers replies.
        """
        replies = await self.platform.get_all_replies(username)
        # Standardize the replies
        standardized_replies = [_reply_tweet_to_interaction(reply, social_account=reply.get("user")) for reply in replies]
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

    async def discover_new_contents(
        self, social_account: models.SocialAccount
    ) -> dict[str, list[models.Post | models.Interaction]]:
        """
        Discover new content (posts and interactions) for a Twitter account.

        Args:
            social_account: SocialAccount data containing platform and account_id

        Returns:
            Dictionary with "posts" and "interactions" keys
        """
        try:
            # Get new interactions to the account, currently only replies
            all_replies = await self.discover_new_interactions(social_account.account_username)

            # Filter replies
            verified_replies: list[models.Interaction] = []
            for reply in all_replies:
                reply_id = reply.interaction_id
                # 1.1 Check if the reply comes from a verified username using the CSV list using user id.
                verified_user_ids = await self.get_verified_users()
                if reply.account_id not in verified_user_ids:
                    logger.info(
                        f"🚫 Reply {reply_id} from unverified account with id {reply.account_id}; skipping."
                    )
                    continue

                # 1.2 Check if the reply comes from an account younger than 1 year.
                account_created_at = datetime.datetime.strptime(
                    reply.extra_data["user"]["created_at"], "%a %b %d %H:%M:%S %z %Y"
                )
                account_age = (
                    datetime.datetime.now(datetime.timezone.utc) - account_created_at
                )
                if account_age.days < 365:
                    logger.info(
                        f"⏳ Reply {reply_id} from account younger than 1 year; skipping."
                    )
                    continue
                
                logger.info(
                        f"⏳ Processing reply {reply_id} from verified account with id {reply.account_id}"
                )
                verified_replies.append(reply)

            # Get parent posts of the replies, these are considered as new posts
            all_parent_post_ids = [
                reply.post_id for reply in all_replies if reply.post_id is not None
            ]

            posts = await asyncio.gather(
                *[self.platform.get_post(post_id) for post_id in all_parent_post_ids], return_exceptions=True
            )
            posts = [_tweet_to_post(post, social_account=post.get("user")) for post in posts if not isinstance(post, Exception)]
            
            # Assign the post to the reply, filter valida replies
            posts_dict = {post.post_id: post for post in posts}
            valid_replies = []
            for reply in verified_replies:
                if reply.post_id in posts_dict.keys():
                    # Reply still has available parent post
                    reply.post = posts_dict[reply.post_id]
                    valid_replies.append(reply)
            
            return {"posts": posts, "interactions": valid_replies}

        except Exception as e:
            logger.error(
                f"❌ Error discovering new contents for {social_account.account_username}: {traceback.format_exc()}"
            )
            return {"posts": [], "interactions": []}

    async def verify_account(
        self, username: str, verification_post_id: str, node: models.Node
    ) -> tuple[models.SocialAccount, Optional[str]]:
        try:
            raw_verification_post = await self.platform.get_post(verification_post_id)
            verification_post = _tweet_to_post(raw_verification_post)
            social_account = _twitter_user_to_social_account(raw_verification_post.get("user"), node=node)
            verification_post.social_account = social_account
            # Check if username is correct
            assert verification_post.social_account.account_username == username, f"Username mismatch: {verification_post.social_account.account_username} != {username}"
            # Check if miner 's hotkey is in the post text
            assert node.node_hotkey in verification_post.content
            # Check if the post quotes the Nuance announcement post
            assert verification_post.extra_data["is_quote_tweet"]
            assert (
                verification_post.extra_data["quoted_status_id"]
                == constants.NUANCE_ANNOUNCEMENT_POST_ID
            )
            return verification_post.social_account, None
        except Exception as e:
            logger.error(
                f"❌ Error verifying account {username} from hotkey {node.node_hotkey}: {traceback.format_exc()}"
            )
            return None, str(e)


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
        account_username=user.get("username"),
        node_hotkey=node.node_hotkey if node else None,
        node_netuid=node.node_netuid if node else None,
        created_at=datetime.datetime.strptime(
            user.get("created_at"), "%a %b %d %H:%M:%S %z %Y"
        ).astimezone(datetime.timezone.utc),
        extra_data=user,
        node=node if node else None,
    )


def _tweet_to_post(tweet: dict, social_account: models.SocialAccount | dict | None = None) -> models.Post:
    """
    Convert a Twitter tweet dictionary to a Post object.
    """
    if social_account is not None and isinstance(social_account, dict):
        social_account = _twitter_user_to_social_account(social_account)
    return models.Post(
        platform_type=models.PlatformType.TWITTER,
        post_id=tweet.get("id"),
        account_id=tweet.get("user", {}).get("id"),
        content=tweet.get("text"),
        created_at=datetime.datetime.strptime(
            tweet.get("created_at"), "%a %b %d %H:%M:%S %z %Y"
        ).astimezone(datetime.timezone.utc),
        extra_data=tweet,
        social_account=social_account,
    )


def _reply_tweet_to_interaction(tweet: dict, social_account: models.SocialAccount=None, post: models.Post=None) -> models.Interaction:
    """
    Convert a Twitter tweet dictionary to an Interaction object.
    """
    if social_account is not None and isinstance(social_account, dict):
        social_account = _twitter_user_to_social_account(social_account)
    if post is not None and isinstance(post, dict):
        post = _tweet_to_post(post)
    return models.Interaction(
        interaction_id=tweet.get("id"),
        platform_type=models.PlatformType.TWITTER,
        interaction_type=models.InteractionType.REPLY,
        account_id=tweet.get("user", {}).get("id"),
        post_id=tweet.get("in_reply_to_status_id"),
        content=tweet.get("text"),
        created_at=datetime.datetime.strptime(
            tweet.get("created_at"), "%a %b %d %H:%M:%S %z %Y"
        ).astimezone(datetime.timezone.utc),
        extra_data=tweet,
        social_account=social_account if social_account else None,
        post=post if post else None,
    )
