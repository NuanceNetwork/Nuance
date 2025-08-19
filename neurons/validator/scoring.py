# neurons/validator/scoring.py
import datetime
import traceback
from typing import Optional

import numpy as np

import nuance.constants as cst
from nuance.database import (
    InteractionRepository,
    PostRepository,
    SocialAccountRepository,
    NodeRepository,
)
import nuance.models as models
from nuance.settings import settings
from nuance.utils.bittensor_utils import get_metagraph
from nuance.utils.logging import logger
from nuance.constitution import constitution_store


class ScoreCalculator:
    """
    Handles score calculations for validator interactions.
    Keeps the current scoring logic but separates it from the main validator class.
    """

    async def calculate_interaction_score(
        self,
        interaction: models.Interaction,
        cutoff_date: datetime.datetime,
        interaction_base_score: float = 1.0,
    ) -> Optional[dict[str, float]]:
        """
        Calculate score for an interaction based on type and engagement weight.

        Args:
            interaction: The interaction to score (must have .post and .social_account set)
            cutoff_date: The date beyond which interactions are not scored
            interaction_base_score: Base score for this interaction

        Returns:
            Dict[str, float]: The calculated score for each category, or None if too old
        """
        logger.debug(
            f"Calculating score for interaction {interaction.interaction_id} with base score {interaction_base_score} from account {interaction.account_id}"
        )

        interaction.created_at = interaction.created_at.replace(
            tzinfo=datetime.timezone.utc
        )

        # Skip if the interaction is too old
        if interaction.created_at < cutoff_date:
            return None

        # Base type weights
        base_score = (
            models.INTERACTION_TYPE_WEIGHTS.get(interaction.interaction_type, 0.5)
            * interaction_base_score
        )

        # Base calculated score (without user ranking and category multiplier)
        calculated_score = base_score

        # Get post topics to determine scoring categories
        post_topics = interaction.post.topics if interaction.post.topics else ["other"]

        interaction_scores: dict[str, float] = {}
        interaction_user_id = interaction.account_id

        # Score for each topic/category the post belongs to
        all_active_topics = await constitution_store.get_topic_weights()
        for topic in post_topics:
            topic_score = calculated_score

            # Determine category and apply engagement weight
            if topic in all_active_topics:
                category = topic
            else:
                continue

            # Get ranked score
            verified_users = await constitution_store.get_verified_users(
                platform=interaction.platform_type, category=category
            )
            rank_multiplier = 0
            for user_data in verified_users:
                if user_data.get("id") == interaction_user_id:
                    rank_multiplier = user_data.get("weight", 0)
                    break

            # Final score with engagement weight
            final_score = topic_score * rank_multiplier
            interaction_scores[topic] = final_score

        return interaction_scores

    async def calculate_post_score(
        self,
        post: models.Post,
        cutoff_date: datetime.datetime,
        post_base_score: float = 1.0,
    ) -> Optional[dict[str, float]]:
        """
        Calculate score for a post based on engagement weight.

        Args:
            post: The post to score
            cutoff_date: The date beyond which posts are not scored
            post_base_score: Base score for this post

        Returns:
            Dict[str, float]: The calculated score for each category, or None if too old
        """
        logger.debug(
            f"Calculating score for post {post.post_id} with base score {post_base_score} from account {post.account_id}"
        )

        post.created_at = post.created_at.replace(tzinfo=datetime.timezone.utc)

        # Skip if the post is too old
        if post.created_at < cutoff_date:
            return None

        # Base type weights
        # One post have same base score as one QRT
        base_score = (
            models.INTERACTION_TYPE_WEIGHTS.get(models.InteractionType.QUOTE)
            * post_base_score
        )

        # Base calculated score (without user ranking and category multiplier)
        calculated_score = base_score

        # Get post topics to determine scoring categories
        post_topics = post.topics if post.topics else ["other"]

        post_scores: dict[str, float] = {}
        post_user_id = post.account_id

        # Score for each topic/category the post belongs to
        all_active_topics = await constitution_store.get_topic_weights()
        for topic in post_topics:
            topic_score = calculated_score

            # Determine category and apply engagement weight
            if topic in all_active_topics:
                category = topic
            else:
                continue

            # Get ranked score
            verified_users = await constitution_store.get_verified_users(
                platform=post.platform_type, category=category
            )
            rank_multiplier = 0
            for user_data in verified_users:
                if user_data.get("id") == post_user_id:
                    rank_multiplier = user_data.get("weight", 0)
                    break

            # Final score with engagement weight
            final_score = topic_score * rank_multiplier
            post_scores[topic] = final_score

        return post_scores

    async def calculate_detailed_scores(
        self,
        recent_posts: list[models.Post],
        recent_interactions: list[models.Interaction],
        cutoff_date: datetime.datetime,
        post_repository: PostRepository,
        account_repository: SocialAccountRepository,
        node_repository: NodeRepository,
    ) -> dict[str, list[dict]]:
        """Returns simplified detailed score breakdown for each post/interaction by miner hotkey."""

        node_detailed_scores: dict[str, list[dict]] = {}
        constitution_config = await constitution_store.get_constitution_config()

        # Filter posts from verified accounts only
        posts_from_verified_users: list[models.Post] = []
        posts_by_platform: dict[str, list[models.Post]] = {
            platform: [] for platform in constitution_config.get("platforms", {})
        }
        for post in recent_posts:
            if post.platform_type in posts_by_platform:
                posts_by_platform[post.platform_type].append(post)

        for platform, posts_on_platform in posts_by_platform.items():
            verified_users_on_platform = await constitution_store.get_verified_users(
                platform=platform
            )
            verified_user_ids_on_platform = [
                user["id"]
                for user in verified_users_on_platform
                if user.get("id") is not None
            ]
            for post in posts_on_platform:
                if post.account_id in verified_user_ids_on_platform:
                    posts_from_verified_users.append(post)

        recent_posts = posts_from_verified_users

        # Calculate base scores per account
        engagement_count_by_account: dict[str, int] = {}
        for interaction in recent_interactions:
            engagement_count_by_account[interaction.account_id] = (
                engagement_count_by_account.get(interaction.account_id, 0) + 1
            )
        for post in recent_posts:
            engagement_count_by_account[post.account_id] = (
                engagement_count_by_account.get(post.account_id, 0) + 1
            )

        base_score_for_account: dict[str, float] = {}
        for account_id, count in engagement_count_by_account.items():
            if count > 0:
                score = 1.0 if count == 1 else 1.7 if count == 2 else 2.0
                score = score / count
            else:
                score = 0.0
            base_score_for_account[account_id] = score

        # Process interactions
        for interaction in recent_interactions:
            try:
                post = await post_repository.get_by(
                    platform_type=interaction.platform_type, post_id=interaction.post_id
                )
                if (
                    not post
                    or post.processing_status != models.ProcessingStatus.ACCEPTED
                ):
                    logger.warning(
                        f"Post not found or not accepted for interaction {interaction.interaction_id}"
                    )
                    continue

                interaction.post = post

                post_account = await account_repository.get_by_platform_id(
                    post.platform_type, post.account_id
                )
                if not post_account:
                    logger.warning(f"Account not found for post {post.post_id}")
                    continue

                interaction_account = await account_repository.get_by_platform_id(
                    interaction.platform_type, interaction.account_id
                )
                if not interaction_account:
                    logger.warning(
                        f"Account not found for interaction {interaction.interaction_id}"
                    )
                    continue
                interaction.social_account = interaction_account

                node = await node_repository.get_by_hotkey_netuid(
                    post_account.node_hotkey, settings.NETUID
                )
                if not node:
                    logger.warning(
                        f"Node not found for account {post_account.account_id}"
                    )
                    continue

                interaction_scores = await self.calculate_interaction_score(
                    interaction=interaction,
                    cutoff_date=cutoff_date,
                    interaction_base_score=base_score_for_account[
                        interaction.account_id
                    ],
                )

                if not interaction_scores:
                    continue

                miner_hotkey = node.node_hotkey
                if miner_hotkey not in node_detailed_scores:
                    node_detailed_scores[miner_hotkey] = []

                node_detailed_scores[miner_hotkey].append(
                    {
                        "type": "interaction",
                        "platform": interaction.platform_type,
                        "id": interaction.interaction_id,
                        "category_scores": interaction_scores,
                    }
                )

            except Exception:
                logger.error(
                    f"Error processing interaction {interaction.interaction_id}: {traceback.format_exc()}"
                )

        # Process posts
        for post in recent_posts:
            try:
                post_account = await account_repository.get_by_platform_id(
                    post.platform_type, post.account_id
                )
                if not post_account:
                    logger.warning(f"Account not found for post {post.post_id}")
                    continue

                node = await node_repository.get_by_hotkey_netuid(
                    post_account.node_hotkey, settings.NETUID
                )
                if not node:
                    logger.warning(
                        f"Node not found for account {post_account.account_id}"
                    )
                    continue

                post_scores = await self.calculate_post_score(
                    post=post,
                    cutoff_date=cutoff_date,
                    post_base_score=base_score_for_account[post.account_id],
                )

                if not post_scores:
                    continue

                miner_hotkey = node.node_hotkey
                if miner_hotkey not in node_detailed_scores:
                    node_detailed_scores[miner_hotkey] = []

                node_detailed_scores[miner_hotkey].append(
                    {
                        "type": "post",
                        "platform": post.platform_type,
                        "id": post.post_id,
                        "category_scores": post_scores,
                    }
                )

            except Exception:
                logger.error(
                    f"Error processing post {post.post_id}: {traceback.format_exc()}"
                )

        return node_detailed_scores

    def aggregate_scores(
        self, detailed_scores: dict[str, list[dict]]
    ) -> dict[str, dict[str, float]]:
        """Aggregate scores from detailed breakdown."""

        node_scores: dict[str, dict[str, float]] = {}

        for hotkey, score_items in detailed_scores.items():
            if hotkey not in node_scores:
                node_scores[hotkey] = {}

            for item in score_items:
                for category, score in item["category_scores"].items():
                    if category not in node_scores[hotkey]:
                        node_scores[hotkey][category] = 0.0
                    node_scores[hotkey][category] += score

        return node_scores

    async def calculate_normalized_scores(
        self,
        recent_posts: list[models.Post],
        recent_interactions: list[models.Interaction],
        cutoff_date: datetime.datetime,
        post_repository: PostRepository,
        account_repository: SocialAccountRepository,
        node_repository: NodeRepository,
    ) -> np.ndarray:
        detailed_scores = await self.calculate_detailed_scores(
            recent_posts=recent_posts,
            recent_interactions=recent_interactions,
            cutoff_date=cutoff_date,
            post_repository=post_repository,
            account_repository=account_repository,
            node_repository=node_repository,
        )

        node_scores = self.aggregate_scores(detailed_scores)

        # Apply normalization logic
        constitution_config = await constitution_store.get_constitution_config()
        constitution_topics = constitution_config.get("topics", {})

        metagraph = await get_metagraph()
        categories_scores = {
            category: np.zeros(len(metagraph.hotkeys))
            for category in list(constitution_topics.keys())
        }
        for hotkey, scores in node_scores.items():
            if hotkey in metagraph.hotkeys:
                for category, score in scores.items():
                    if category in categories_scores:
                        categories_scores[category][metagraph.hotkeys.index(hotkey)] = (
                            score
                        )

        # Normalize scores for each category
        for category in categories_scores:
            categories_scores[category] = np.nan_to_num(categories_scores[category], 0)
            if np.sum(categories_scores[category]) > 0:
                categories_scores[category] = categories_scores[category] / np.sum(
                    categories_scores[category]
                )
            else:
                categories_scores[category] = np.zeros_like(categories_scores[category])

        # Weighted sum of categories for final scores
        final_scores = np.zeros(len(metagraph.hotkeys))
        for category in categories_scores:
            final_scores += categories_scores[category] * constitution_topics.get(
                category, {}
            ).get("weight", 0.0)

        return final_scores

    async def calculate_aggregated_scores(
        self,
        recent_posts: list[models.Post],
        recent_interactions: list[models.Interaction],
        cutoff_date: datetime.datetime,
        post_repository: PostRepository,
        account_repository: SocialAccountRepository,
        node_repository: NodeRepository,
    ):
        node_scores: dict[str, dict[str, float]] = {}  # {hotkey: {category: score}}

        constitution_config = await constitution_store.get_constitution_config()

        # Filter posts, only posts from verified accounts are kept
        posts_from_verified_users: list[models.Post] = []

        posts_by_platform: dict[str, list[models.Post]] = {
            platform: [] for platform in constitution_config.get("platforms", {})
        }
        for post in recent_posts:
            if post.platform_type in posts_by_platform:
                posts_by_platform[post.platform_type].append(post)
        for platform, posts_on_platform in posts_by_platform.items():
            verifed_users_on_platform = await constitution_store.get_verified_users(
                platform=platform
            )
            verifed_user_ids_on_platform = [
                user["id"]
                for user in verifed_users_on_platform
                if user.get("id") is not None
            ]
            for post in posts_on_platform:
                if post.account_id in verifed_user_ids_on_platform:
                    posts_from_verified_users.append(post)

        recent_posts = posts_from_verified_users

        # Calculate base score for each accounts by how many engagements (interactions or posts from verified accounts) they made
        engagement_count_by_account: dict[str, int] = {}  # {account_id: count}

        # Count interactions by account
        for interaction in recent_interactions:
            engagement_count_by_account[interaction.account_id] = (
                engagement_count_by_account.get(interaction.account_id, 0) + 1
            )

        # Count post by account
        for post in recent_posts:
            engagement_count_by_account[post.account_id] = (
                engagement_count_by_account.get(post.account_id, 0) + 1
            )

        base_score_for_account: dict[str, float] = {}
        for account_id, count in engagement_count_by_account.items():
            if count > 0:
                score = 1.0 if count == 1 else 1.7 if count == 2 else 2.0
                score = score / count
            else:
                score = 0.0

            base_score_for_account[account_id] = score

        # Process each interaction
        for interaction in recent_interactions:
            try:
                # Get the post being interacted with
                post = await post_repository.get_by(
                    platform_type=interaction.platform_type, post_id=interaction.post_id
                )
                if not post:
                    logger.warning(
                        f"Post not found for interaction {interaction.interaction_id}"
                    )
                    continue
                elif post.processing_status != models.ProcessingStatus.ACCEPTED:
                    logger.warning(
                        f"Post {post.post_id} is not accepted for interaction {interaction.interaction_id}"
                    )
                    continue

                interaction.post = post

                # Get the account that made the post (miner's account)
                post_account = await account_repository.get_by_platform_id(
                    post.platform_type, post.account_id
                )
                if not post_account:
                    logger.warning(f"Account not found for post {post.post_id}")
                    continue

                # Get the account that made the interaction
                interaction_account = await account_repository.get_by_platform_id(
                    interaction.platform_type, interaction.account_id
                )
                if not interaction_account:
                    logger.warning(
                        f"Account not found for interaction {interaction.interaction_id}"
                    )
                    continue
                interaction.social_account = interaction_account

                # Get the node that owns the account
                node = await node_repository.get_by_hotkey_netuid(
                    post_account.node_hotkey, settings.NETUID
                )
                if not node:
                    logger.warning(
                        f"Node not found for account {post_account.account_id}"
                    )
                    continue

                interaction_scores = await self.calculate_interaction_score(
                    interaction=interaction,
                    cutoff_date=cutoff_date,
                    interaction_base_score=base_score_for_account[
                        interaction.account_id
                    ],
                )

                if not interaction_scores:
                    continue

                # Add to node's score
                miner_hotkey = node.node_hotkey
                if miner_hotkey not in node_scores:
                    node_scores[miner_hotkey] = {}
                for category, score in interaction_scores.items():
                    if category not in node_scores[miner_hotkey]:
                        node_scores[miner_hotkey][category] = 0.0
                    node_scores[miner_hotkey][category] += score

            except Exception:
                logger.error(
                    f"Error scoring interaction {interaction.interaction_id}: {traceback.format_exc()}"
                )

        # Process each post
        for post in recent_posts:
            try:
                # Get the account that made the post (verified account)
                post_account = await account_repository.get_by_platform_id(
                    post.platform_type, post.account_id
                )
                if not post_account:
                    logger.warning(f"Account not found for post {post.post_id}")
                    continue

                # Get the node that owns the account
                node = await node_repository.get_by_hotkey_netuid(
                    post_account.node_hotkey, settings.NETUID
                )
                if not node:
                    logger.warning(
                        f"Node not found for account {post_account.account_id}"
                    )
                    continue

                # Calculate score for this post
                post_scores = await self.calculate_post_score(
                    post=post,
                    cutoff_date=cutoff_date,
                    post_base_score=base_score_for_account[post.account_id],
                )

                if not post_scores:
                    continue

                # Add to node's score
                miner_hotkey = node.node_hotkey
                if miner_hotkey not in node_scores:
                    node_scores[miner_hotkey] = {}
                for category, score in post_scores.items():
                    if category not in node_scores[miner_hotkey]:
                        node_scores[miner_hotkey][category] = 0.0
                    node_scores[miner_hotkey][category] += score
            except Exception:
                logger.error(
                    f"Error scoring post {post.post_id}: {traceback.format_exc()}"
                )

        return node_scores

    # deprecated
    async def aggregate_interaction_scores(
        self,
        recent_interactions: list[models.Interaction],
        cutoff_date: datetime.datetime,
        post_repository: PostRepository,
        account_repository: SocialAccountRepository,
        node_repository: NodeRepository,
    ) -> dict[str, dict[str, float]]:
        """
        Process a list of interactions and return aggregated node scores.

        Args:
            recent_interactions: List of interactions to process
            cutoff_date: Cutoff date for scoring
            repositories: Database repositories for lookups

        Returns:
            dict: {hotkey: {category: score}}
        """
        node_scores: dict[str, dict[str, float]] = {}  # {hotkey: {category: score}}
        interaction_count_by_account: dict[str, int] = {}  # {account_id: count}

        # Count interactions by account
        for interaction in recent_interactions:
            interaction_count_by_account[interaction.account_id] = (
                interaction_count_by_account.get(interaction.account_id, 0) + 1
            )

        # Process each interaction
        for interaction in recent_interactions:
            try:
                # Get the post being interacted with
                post = await post_repository.get_by(
                    platform_type=interaction.platform_type, post_id=interaction.post_id
                )
                if not post:
                    logger.warning(
                        f"Post not found for interaction {interaction.interaction_id}"
                    )
                    continue
                elif post.processing_status != models.ProcessingStatus.ACCEPTED:
                    logger.warning(
                        f"Post {post.post_id} is not accepted for interaction {interaction.interaction_id}"
                    )
                    continue

                interaction.post = post

                # Get the account that made the post (miner's account)
                post_account = await account_repository.get_by_platform_id(
                    post.platform_type, post.account_id
                )
                if not post_account:
                    logger.warning(f"Account not found for post {post.post_id}")
                    continue

                # Get the account that made the interaction
                interaction_account = await account_repository.get_by_platform_id(
                    interaction.platform_type, interaction.account_id
                )
                if not interaction_account:
                    logger.warning(
                        f"Account not found for interaction {interaction.interaction_id}"
                    )
                    continue
                interaction.social_account = interaction_account

                # Get the node that owns the account
                node = await node_repository.get_by_hotkey_netuid(
                    post_account.node_hotkey, settings.NETUID
                )
                if not node:
                    logger.warning(
                        f"Node not found for account {post_account.account_id}"
                    )
                    continue

                # Get node (miner) for scoring
                miner_hotkey = node.node_hotkey

                # Calculate score for this interaction
                interaction_scores = await self.calculate_interaction_score(
                    interaction=interaction,
                    cutoff_date=cutoff_date,
                    interaction_base_score=2.0
                    / interaction_count_by_account[interaction.account_id],
                )

                if not interaction_scores:
                    continue

                # Add to node's score
                if miner_hotkey not in node_scores:
                    node_scores[miner_hotkey] = {}
                for category, score in interaction_scores.items():
                    if category not in node_scores[miner_hotkey]:
                        node_scores[miner_hotkey][category] = 0.0
                    node_scores[miner_hotkey][category] += score

            except Exception as e:
                logger.error(
                    f"Error scoring interaction {interaction.interaction_id}: {e}"
                )

        return node_scores
