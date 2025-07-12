# neurons/validator/scoring.py
import datetime
from typing import Optional

import nuance.constants as cst
from nuance.database import (
    InteractionRepository,
    PostRepository,
    SocialAccountRepository,
    NodeRepository,
)
import nuance.models as models
from nuance.settings import settings
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
        Calculate score for an interaction based on type, recency, and engagement weight.

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

        interaction.created_at = interaction.created_at.replace(tzinfo=datetime.timezone.utc)
        
        # Skip if the interaction is too old
        if interaction.created_at < cutoff_date:
            return None

        # Base type weights
        base_score = models.INTERACTION_TYPE_WEIGHTS.get(interaction.interaction_type, 0.5) * interaction_base_score

        # Recency factor - newer interactions get higher scores
        now = datetime.datetime.now(tz=datetime.timezone.utc)
        age_days = (now - interaction.created_at).days
        max_age = cst.SCORING_WINDOW  # Max age in days

        # Linear decay from 1.0 (today) to 0.1
        recency_factor = max(0.1, 1.0 - (0.9 * age_days / max_age))

        # Base calculated score (without user ranking and category multiplier)
        calculated_score = base_score * recency_factor

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
            verified_users = await constitution_store.get_verified_users(platform=interaction.platform_type, category=category)
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
        Calculate score for a interaction based on recency, and engagement weight.

        Args:
            post: The interaction to score
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
        base_score = models.INTERACTION_TYPE_WEIGHTS.get(models.InteractionType.QUOTE) * post_base_score

        # Recency factor - newer posts get higher scores
        now = datetime.datetime.now(tz=datetime.timezone.utc)
        age_days = (now - post.created_at).days
        max_age = cst.SCORING_WINDOW  # Max age in days

        # Linear decay from 1.0 (today) to 0.1
        recency_factor = max(0.1, 1.0 - (0.9 * age_days / max_age))

        # Base calculated score (without user ranking and category multiplier)
        calculated_score = base_score * recency_factor

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
            verified_users = await constitution_store.get_verified_users(platform=post.platform_type, category=category)
            rank_multiplier = 0
            for user_data in verified_users:
                if user_data.get("id") == post_user_id:
                    rank_multiplier = user_data.get("weight", 0)
                    break
            
            # Final score with engagement weight
            final_score = topic_score * rank_multiplier
            post_scores[topic] = final_score

        return post_scores
    
    async def aggregate_scores(
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
            platform: [] for platform in constitution_config.get("platform", {})
        }
        for post in recent_posts:
            if post.platform_type in posts_by_platform:
                posts_by_platform[post.platform_type].append(post)

        for platform, posts_on_platform in posts_by_platform.items():
            verifed_users_on_platform = await constitution_store.get_verified_users(platform=platform)
            for post in posts_on_platform:
                if post.account_id in verifed_users_on_platform:
                    posts_from_verified_users.append(post)
        
        recent_posts = posts_from_verified_users

        work_count_by_account: dict[str, int] = {}  # {account_id: count}
        # Count interactions by account
        for interaction in recent_interactions:
            work_count_by_account[interaction.account_id] = (
                work_count_by_account.get(interaction.account_id, 0) + 1
            )
        # Count post by account
        for post in recent_posts:
            work_count_by_account[post.account_id] = (
                work_count_by_account.get(post.account_id, 0) + 1
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

                interaction_scores = await self.calculate_interaction_score(
                    interaction=interaction,
                    cutoff_date=cutoff_date,
                    interaction_base_score=2.0
                    / work_count_by_account[interaction.account_id],
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

            except Exception as e:
                logger.error(
                    f"Error scoring interaction {interaction.interaction_id}: {e}"
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
                    post_base_score=2.0
                    / work_count_by_account[interaction.account_id],
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
            except Exception as e:
                logger.error(
                    f"Error scoring post {post.post_id}: {e}"
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
