# nuance/social/discovery/twitter.py
import asyncio
import csv
import datetime
import json
import time
from typing import Optional
import traceback

import aiohttp

import nuance.constants as cst
import nuance.models as models
from nuance.utils.logging import logger
from nuance.utils.networking import async_http_request_with_retry
from nuance.social.discovery.base import BaseDiscoveryStrategy
from nuance.social.platforms.twitter import TwitterPlatform
from nuance.constitution import constitution_store


class TwitterDiscoveryStrategy(BaseDiscoveryStrategy[TwitterPlatform]):
    def __init__(self, platform: Optional[TwitterPlatform] = None):
        if platform is None:
            platform = TwitterPlatform()

        super().__init__(platform)

        # self._verified_users_cache: dict[str, Any] = {
        #     "verified_user_ids": set(),
        #     "last_updated": None,
        # }
        # self._cache_lock = asyncio.Lock()

    async def get_post(self, post_id: str) -> models.Post:
        raw_post = await self.platform.get_post(post_id)
        return _tweet_to_post(raw_post, social_account=raw_post.get("user"))
    
    async def get_interaction(self, interaction_id: str) -> models.Interaction:
        # We only support replies and quotes retweet at the moment and they are Tweets
        raw_interaction = await self.platform.get_post(interaction_id)
        return _tweet_to_interaction(raw_interaction, social_account=raw_interaction.get("user"))

    async def discover_new_posts(self, username: str) -> list[models.Post]:
        try:
            raw_posts = await self.platform.get_all_posts(username)
            return [
                _tweet_to_post(post, social_account=post.get("user"))
                for post in raw_posts
            ]
        except Exception as e:
            logger.error(
                f"❌ Error discovering new posts for {username}: {traceback.format_exc()}"
            )
            return []

    async def discover_new_interactions(
        self, username: str, account_id: str
    ) -> list[models.Interaction]:
        """
        Discover new interactions for a Twitter account. This method currently only discovers replies.
        """
        replies = await self.platform.get_all_replies(username)
        # Standardize the replies
        standardized_replies = [
            _tweet_to_interaction(
                reply,
                social_account=reply.get("user"),
            )
            for reply in replies
        ]

        # Fetch quotes
        quotes = await self.platform.get_all_quotes(account_id)
        standardized_quotes = [
            _tweet_to_interaction(
                quote,
                social_account=quote.get("user"),
            )
            for quote in quotes
        ]
        return standardized_replies + standardized_quotes

    # async def get_verified_users(self) -> set[str]:
    #     """
    #     Get a set of verified Twitter user IDs.
    #     Maintains a cache that refreshes periodically.

    #     Returns:
    #         Set of verified user IDs
    #     """
    #     current_time = time.time()

    #     # Check if update is needed without acquiring the lock
    #     if (
    #         self._verified_users_cache["last_updated"] is None
    #         or current_time - self._verified_users_cache["last_updated"]
    #         > cst.NUANCE_CONSTITUTION_UPDATE_INTERVAL
    #     ):
    #         # Only acquire the lock if update might be needed
    #         async with self._cache_lock:
    #             # Re-check after acquiring the lock (another task might have updated meanwhile)
    #             if (
    #                 self._verified_users_cache["last_updated"] is None
    #                 or current_time - self._verified_users_cache["last_updated"]
    #                 > cst.NUANCE_CONSTITUTION_UPDATE_INTERVAL
    #             ):
    #                 try:
    #                     # Use github API to list all verified users files on store
    #                     repo_path = cst.NUANCE_CONSTITUTION_STORE_URL.replace(
    #                         "https://github.com/", ""
    #                     )
    #                     api_url = f"https://api.github.com/repos/{repo_path}/contents/verified_users/twitter"

    #                     async with aiohttp.ClientSession() as session:
    #                         # First get list of all CSV files in the directory
    #                         api_response = await async_http_request_with_retry(
    #                             session, "GET", api_url
    #                         )
    #                         verified_users_files: list[dict] = api_response

    #                         all_user_ids = set()

    #                         # Process each CSV file
    #                         for verified_users_file in verified_users_files:
    #                             if not (
    #                                 isinstance(verified_users_file.get("name"), str)
    #                                 and verified_users_file.get("name").endswith(".csv")
    #                                 and isinstance(
    #                                     verified_users_file.get("download_url"), str
    #                                 )
    #                             ):
    #                                 continue

    #                             verified_users_file_url = verified_users_file.get("download_url")
    #                             try:
    #                                 csv_data = await async_http_request_with_retry(
    #                                     session, "GET", verified_users_file_url
    #                                 )
    #                                 # Process the CSV data
    #                                 lines = csv_data.splitlines()
    #                                 reader = csv.DictReader(lines)
    #                                 file_user_ids = {
    #                                     row["id"] for row in reader if "id" in row
    #                                 }

    #                                 all_user_ids.update(file_user_ids)
                                    
    #                                 logger.debug(
    #                                     f"✅ Processed {verified_users_file["name"]}, added {len(file_user_ids)} users"
    #                                 )
    #                             except Exception as e:
    #                                 logger.error(
    #                                     f"❌ Error processing {verified_users_file["name"]}: {str(e)}"
    #                                 )
    #                                 continue

    #                         # Update cache
    #                         self._verified_users_cache["verified_user_ids"] = all_user_ids
    #                         self._verified_users_cache["last_updated"] = current_time

    #                         logger.info(
    #                             f"✅ Fetched verified Twitter users from {len(verified_users_files)} files. "
    #                             f"Total unique users: {len(all_user_ids)}"
    #                         )

    #                 except Exception as e:
    #                     logger.error(
    #                         f"❌ Error fetching verified Twitter users: {traceback.format_exc()}"
    #                     )

    #     return self._verified_users_cache["verified_user_ids"]

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
            all_interactions = await self.discover_new_interactions(
                social_account.account_username, social_account.account_id
            )

            # Filter interactions
            verified_interactions: list[models.Interaction] = []
            for interaction in all_interactions:
                interaction_id = interaction.interaction_id
                # 1.1 Check if the interaction comes from a verified username using the CSV list using user id.
                verified_user_ids = await constitution_store.get_verified_user_ids(models.PlatformType.TWITTER)
                if interaction.account_id not in verified_user_ids:
                    logger.info(
                        f"🚫 Interaction {interaction_id} from unverified account with id {interaction.account_id}; skipping."
                    )
                    continue

                # 1.2 Check if the interaction comes from an account younger than 1 year.
                account_created_at = datetime.datetime.strptime(
                    interaction.extra_data["user"]["created_at"],
                    "%a %b %d %H:%M:%S %z %Y",
                )
                account_age = (
                    datetime.datetime.now(datetime.timezone.utc) - account_created_at
                )
                if account_age.days < 365:
                    logger.info(
                        f"⏳ Interaction {interaction_id} from account younger than 1 year; skipping."
                    )
                    continue

                logger.info(
                    f"✅ {interaction_id} from verified account with id {interaction.account_id} discovered"
                )
                verified_interactions.append(interaction)

            # Get parent posts of the replies, these are considered as new posts
            all_parent_post_ids = [
                reply.post_id for reply in all_interactions if reply.post_id is not None
            ]

            posts = await asyncio.gather(
                *[self.platform.get_post(post_id) for post_id in all_parent_post_ids],
                return_exceptions=True,
            )
            posts = [
                _tweet_to_post(post, social_account=post.get("user"))
                for post in posts
                if not isinstance(post, Exception)
            ]

            # Assign the post to the reply, filter valid interactions
            posts_dict = {post.post_id: post for post in posts}
            valid_interactions = []
            for interaction in verified_interactions:
                if interaction.post_id in posts_dict.keys():
                    # Reply still has available parent post
                    interaction.post = posts_dict[interaction.post_id]
                    valid_interactions.append(interaction)

            return {"posts": posts, "interactions": valid_interactions}

        except Exception as e:
            logger.error(
                f"❌ Error discovering new contents for {social_account.account_username}: {traceback.format_exc()}"
            )
            return {"posts": [], "interactions": []}

    async def verify_account(
        self, 
        username: Optional[str] = None, 
        account_id: Optional[str] = None,
        verification_post_id: str = None,
        node: models.Node = None
    ) -> tuple[models.SocialAccount, Optional[str]]:
        try:
            raw_verification_post = await self.platform.get_post(verification_post_id)
            verification_post = _tweet_to_post(raw_verification_post)
            social_account = _twitter_user_to_social_account(
                raw_verification_post.get("user"), node=node
            )
            verification_post.social_account = social_account
            
            # Check if username is correct (if provided)
            if username:
                assert verification_post.social_account.account_username == username, (
                    f"Username mismatch: {verification_post.social_account.account_username} != {username}"
                )
            
            # Check if account_id is correct (if provided)
            if account_id:
                assert verification_post.social_account.account_id == account_id, (
                    f"Account ID mismatch: {verification_post.social_account.account_id} != {account_id}"
                )
                
            # Check if miner's hotkey is in the post text
            assert node.node_hotkey in verification_post.content
            # Check if the post quotes the Nuance announcement post
            assert verification_post.extra_data["is_quote_tweet"]
            assert (
                verification_post.extra_data["quoted_status_id"]
                == cst.NUANCE_ANNOUNCEMENT_POST_ID
            )
            return verification_post.social_account, None
        except Exception as e:
            identifier = username or account_id or "unknown"
            logger.error(
                f"❌ Error verifying account {identifier} from hotkey {node.node_hotkey}: {traceback.format_exc()}"
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


def _tweet_to_post(
    tweet: dict, social_account: models.SocialAccount | dict | None = None
) -> models.Post:
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


def _tweet_to_interaction(
    tweet: dict,
    social_account: models.SocialAccount = None,
    post: models.Post = None,
    # interaction_type: models.InteractionType = models.InteractionType.REPLY,
) -> models.Interaction:
    """
    Convert a Twitter tweet dictionary to an Interaction object.
    """
    if social_account is not None and isinstance(social_account, dict):
        social_account = _twitter_user_to_social_account(social_account)
    if post is not None and isinstance(post, dict):
        post = _tweet_to_post(post)

    # process interaction_type
    if tweet.get("is_quote_tweet") is True:
        interaction_type = models.InteractionType.QUOTE
        post_id = tweet.get("quoted_status_id")
    else:
        interaction_type = models.InteractionType.REPLY
        post_id = tweet.get("in_reply_to_status_id")

    return models.Interaction(
        interaction_id=tweet.get("id"),
        platform_type=models.PlatformType.TWITTER,
        interaction_type=interaction_type,
        account_id=tweet.get("user", {}).get("id"),
        post_id=post_id,
        content=tweet.get("text"),
        created_at=datetime.datetime.strptime(
            tweet.get("created_at"), "%a %b %d %H:%M:%S %z %Y"
        ).astimezone(datetime.timezone.utc),
        extra_data=tweet,
        social_account=social_account if social_account else None,
        post=post if post else None,
    )
