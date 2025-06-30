from loguru import logger
import datetime
import asyncio
from typing import Optional
import traceback

from nuance.database import (
    PostRepository,
    InteractionRepository,
    SocialAccountRepository,
    NodeRepository,
)
from nuance.database.engine import get_db_session
import nuance.models as models
import nuance.constants as cst
from nuance.constitution import constitution_store
from nuance.settings import settings
import numpy as np
import math
from nuance.utils.bittensor_utils import get_subtensor, get_wallet, get_metagraph

class Test:
    async def initialize(self):
        # Initialize components and repositories
        # self.social = SocialContentProvider()
        # self.pipelines = {
        #     "post": PipelineFactory.create_post_pipeline(),
        #     "interaction": PipelineFactory.create_interaction_pipeline(),
        # }
        self.post_repository = PostRepository(get_db_session)
        self.interaction_repository = InteractionRepository(get_db_session)
        self.account_repository = SocialAccountRepository(get_db_session)
        self.node_repository = NodeRepository(get_db_session)

        # Initialize bittensor objects
        self.subtensor = await get_subtensor()
        self.wallet = await get_wallet()
        self.metagraph = await get_metagraph()
        
        # Check if validator is registered to chain
        if self.wallet.hotkey.ss58_address not in self.metagraph.hotkeys:
            logger.error(
                f"\nYour validator: {self.wallet} is not registered to chain connection: {self.subtensor} \nRun 'btcli register' and try again."
            )
            exit()
        else:
            self.uid = self.metagraph.hotkeys.index(self.wallet.hotkey.ss58_address)
            logger.info(f"Running validator on uid: {self.uid}")

        # Start workers
        self.workers = [
            # asyncio.create_task(self.content_discovering()),
            # asyncio.create_task(self.post_processing()),
            # asyncio.create_task(self.interaction_processing()),
            asyncio.create_task(self.score_aggregating()),
        ]

        logger.info("Validator initialized successfully")

    async def score_aggregating(self):
        """
        Calculate scores for all nodes based on recent interactions.
        This method periodically queries for interactions from the last 14 days,
        scores them based on freshness and account influence, and updates node scores.
        """
        while True:
            try:
                # Get current block for score tracking
                current_block = await self.subtensor.get_current_block()
                logger.info(f"Calculating scores for block {current_block}")

                # Get cutoff date (14 days ago)
                cutoff_date = datetime.datetime.now(
                    tz=datetime.timezone.utc
                ) - datetime.timedelta(days=14)

                # Get constitution config
                constitution_config = await constitution_store.get_constitution_config()
                constitution_topics = constitution_config.get("topics", {})

                # 1. Get all interactions from the last 14 days that are PROCESSED and ACCEPTED
                recent_interactions = (
                    await self.interaction_repository.get_recent_interactions(
                        cutoff_date=cutoff_date,
                        processing_status=models.ProcessingStatus.ACCEPTED
                    )
                )

                if not recent_interactions:
                    logger.info("No recent interactions found for scoring")
                    await asyncio.sleep(cst.EPOCH_LENGTH)
                    continue

                logger.info(
                    f"Found {len(recent_interactions)} recent interactions for scoring"
                )

                # 2. Calculate scores for all miners (keyed by hotkey)
                node_scores: dict[str, dict[str, float]] = {} # {hotkey: {category: score}}
                interaction_count_by_account: dict[str, int] = {} # {account_id: count}

                # 2.1 Count interactions by account
                for interaction in recent_interactions:
                    interaction_count_by_account[interaction.account_id] = interaction_count_by_account.get(interaction.account_id, 0) + 1

                # 2.2 Calculate scores for all miners
                for interaction in recent_interactions:
                    try:
                        # Get the post being interacted with
                        post = await self.post_repository.get_by(
                            platform_type=interaction.platform_type,
                            post_id=interaction.post_id
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
                        post_account = await self.account_repository.get_by_platform_id(
                            post.platform_type, post.account_id
                        )
                        if not post_account:
                            logger.warning(f"Account not found for post {post.post_id}")
                            continue

                        # Get the account that made the interaction
                        interaction_account = (
                            await self.account_repository.get_by_platform_id(
                                interaction.platform_type, interaction.account_id
                            )
                        )
                        if not interaction_account:
                            logger.warning(
                                f"Account not found for interaction {interaction.interaction_id}"
                            )
                            continue
                        interaction.social_account = interaction_account

                        # Get the node that own the account
                        node = await self.node_repository.get_by_hotkey_netuid(
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
                        interaction_scores = self._calculate_interaction_score(
                            interaction=interaction,
                            cutoff_date=cutoff_date,
                            interaction_base_score=2.0 / interaction_count_by_account[interaction.account_id],
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

                    except Exception:
                        logger.error(
                            f"Error scoring interaction {interaction.interaction_id}: {traceback.format_exc()}"
                        )

                # 3. Set weights for all nodes
                # We create a score array for each category
                categories_scores = {category: np.zeros(len(self.metagraph.hotkeys)) for category in list(constitution_topics.keys())}
                for hotkey, scores in node_scores.items():
                    if hotkey in self.metagraph.hotkeys:
                        for category, score in scores.items():
                            categories_scores[category][self.metagraph.hotkeys.index(hotkey)] = score
                            
                # Normalize scores for each category
                for category in categories_scores:
                    categories_scores[category] = np.nan_to_num(categories_scores[category], 0)
                    if np.sum(categories_scores[category]) > 0:
                        categories_scores[category] = categories_scores[category] / np.sum(categories_scores[category])
                    else:
                        categories_scores[category] = np.ones(len(self.metagraph.hotkeys)) / len(self.metagraph.hotkeys)
                        
                # Weighted sum of categories
                scores = np.zeros(len(self.metagraph.hotkeys))
                for category in categories_scores:
                    scores += categories_scores[category] * constitution_topics.get(category, {}).get("weight", 0.0)
                
                scores_weights = scores.tolist()

                # Burn
                alpha_burn_weights = [0.0] * len(self.metagraph.hotkeys)
                # owner_hotkey = "5HN1QZq7MyGnutpToCZGdiabP3D339kBjKXfjb1YFaHacdta"
                # owner_hotkey_index = self.metagraph.hotkeys.index(owner_hotkey)
                # logger.info(f"🔥 Burn alpha by setting weight for uid {owner_hotkey_index} - {owner_hotkey} (owner's hotkey): 1")
                # alpha_burn_weights[owner_hotkey_index] = 1
                
                # Combine weights
                alpha_burn_ratio = 0.7
                combined_weights = [
                    (alpha_burn_ratio * alpha_burn_weight) + ((1 - alpha_burn_ratio) * score_weight)
                    for alpha_burn_weight, score_weight in zip(alpha_burn_weights, scores_weights)
                ]

                logger.info(f"Weights: {combined_weights}")
                # 4. Update metagraph with new weights
                # await self.subtensor.set_weights(
                #     wallet=self.wallet,
                #     netuid=settings.NETUID,
                #     uids=list(range(len(combined_weights))),
                #     weights=combined_weights,
                # )
                logger.info(f"✅ Updated weights on block {current_block}.")

                # Wait before next scoring cycle
                await asyncio.sleep(cst.EPOCH_LENGTH)

            except Exception as e:
                logger.error(f"Error in score aggregation: {traceback.format_exc()}")
                await asyncio.sleep(10)  # Backoff on error


    def _calculate_interaction_score(
        self,
        interaction: models.Interaction,
        cutoff_date: datetime.datetime,
        interaction_base_score: float = 1.0,
    ) -> Optional[dict[str, float]]:
        """
        Calculate score for an interaction based on type, recency, and account influence.

        Args:
            interaction: The interaction to score
            interaction_account: The account that made the interaction
            cutoff_date: The date beyond which interactions are not scored (14 days ago)

        Returns:
            dict[str, float]: The calculated score for each category
        """
        logger.debug(f"Calculating score for interaction {interaction.interaction_id} with base score {interaction_base_score} having account {interaction.account_id}")
        interaction.created_at = interaction.created_at.replace(tzinfo=datetime.timezone.utc)
        # Skip if the interaction is too old
        if interaction.created_at < cutoff_date:
            return None

        base_score = models.INTERACTION_TYPE_WEIGHTS.get(interaction.interaction_type, 0.5) * interaction_base_score

        # Recency factor - newer interactions get higher scores
        now = datetime.datetime.now(tz=datetime.timezone.utc)
        age_days = (now - interaction.created_at).days
        max_age = 14  # Max age in days

        # Linear decay from 1.0 (today) to 0.1 (14 days old)
        recency_factor = 1.0 - (0.9 * age_days / max_age)

        # Account influence factor (based on followers)
        followers = interaction.social_account.extra_data.get("followers_count", 0)
        influence_factor = min(1.0, followers / 10000)  # Cap at 1.0
        
        score = base_score * recency_factor * math.log(1 + influence_factor)
        
        # Scores for categories / topics (all same as score above)
        post_topics = interaction.post.topics
        if not post_topics:
            interaction_scores: dict[str, float] = {"other": score}
        else:
            interaction_scores: dict[str, float] = {
                topic: score for topic in post_topics
            }
        
        return interaction_scores

if __name__ == "__main__":
    test = Test()
    loop = asyncio.get_event_loop()
    loop.run_until_complete(test.initialize())
    loop.run_forever()