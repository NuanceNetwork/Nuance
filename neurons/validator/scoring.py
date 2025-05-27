# neurons/validator/scoring.py
import asyncio
import datetime
import math
import time
from typing import Optional

import nuance.constants as cst
from nuance.database import (
    PostRepository,
    InteractionRepository,
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
        type_weights = {
            models.InteractionType.REPLY: 1.0,
            models.InteractionType.QUOTE: 3.0,
        }

        base_score = type_weights.get(interaction.interaction_type, 0.5) * interaction_base_score

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
        for topic in post_topics:
            topic_score = calculated_score
            
            # Determine category and apply engagement weight
            if topic == "nuance_subnet":
                category = "nuance_subnet"
            elif topic == "bittensor": 
                category = "bittensor"
            else:
                category = "other"
            
            # Get ranked score
            platform_verified_users = await constitution_store.get_verified_users_by_platform_and_category(interaction.platform_type)
            this_category_verified_users = platform_verified_users.get(category, {})
            rank_multiplier = this_category_verified_users.get(interaction_user_id, {}).get("weight", "0")
            
            # Final score with engagement weight
            final_score = topic_score * rank_multiplier
            interaction_scores[topic] = final_score

        return interaction_scores

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

                if interaction_scores is None:
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
