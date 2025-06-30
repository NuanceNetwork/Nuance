import asyncio
import datetime
import traceback

import numpy as np
from nuance.utils.logging import logger

import nuance.constants as cst
import nuance.models as models
from neurons.validator.scoring import ScoreCalculator
from nuance.database import (
    InteractionRepository,
    NodeRepository,
    PostRepository,
    SocialAccountRepository,
)
from nuance.database.engine import get_db_session
from nuance.utils.bittensor_utils import (
    get_metagraph, 
)


all_topic_db = "normal.db"
one_topic_dont_have_interactioon = "dont_have_nuance_topic.db"

async def main():
    interaction_repository = InteractionRepository(get_db_session)
    score_calculator = ScoreCalculator()
    post_repository = PostRepository(get_db_session)
    account_repository = SocialAccountRepository(get_db_session)
    node_repository = NodeRepository(get_db_session)
    metagraph = await get_metagraph()
    while True:
        try:
            # Get cutoff date
            cutoff_date = datetime.datetime.now(
                tz=datetime.timezone.utc
            ) - datetime.timedelta(days=cst.SCORING_WINDOW)

            # 1. Get all interactions from the last SCORING_WINDOW days that are PROCESSED and ACCEPTED
            recent_interactions = (
                await interaction_repository.get_recent_interactions(
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

            # 2. Calculate scores for all miners (use ScoreCalculator)
            node_scores = await score_calculator.aggregate_interaction_scores(
                recent_interactions=recent_interactions,
                cutoff_date=cutoff_date,
                post_repository=post_repository,
                account_repository=account_repository,
                node_repository=node_repository
            )

            # 3. Set weights for all nodes
            # We create a score array for each category
            categories_scores = {category: np.zeros(len(metagraph.hotkeys)) for category in list(cst.CATEGORIES_WEIGHTS.keys())}
            for hotkey, scores in node_scores.items():
                if hotkey in metagraph.hotkeys:
                    for category, score in scores.items():
                        categories_scores[category][metagraph.hotkeys.index(hotkey)] = score
                        
            # Normalize scores for each category
            for category in categories_scores:
                categories_scores[category] = np.nan_to_num(categories_scores[category], 0)
                if np.sum(categories_scores[category]) > 0:
                    categories_scores[category] = categories_scores[category] / np.sum(categories_scores[category])
                else:
                    # categories_scores[category] = np.ones(len(self.metagraph.hotkeys)) / len(self.metagraph.hotkeys) # this will make all miner have weight of this category if no one score any
                    # now we add the category to burned instead
                    scores = np.zeros(len(metagraph.hotkeys))
                    owner_hotkey = "5HN1QZq7MyGnutpToCZGdiabP3D339kBjKXfjb1YFaHacdta"
                    owner_hotkey_index = metagraph.hotkeys.index(owner_hotkey)
                    logger.info(f"🔥 Burn alpha of category {category} by setting weight for uid {owner_hotkey_index} - {owner_hotkey} (owner's hotkey): 1")
                    scores[owner_hotkey_index] = 1
                    categories_scores[category] = scores

                positive_score_uid = np.where(categories_scores[category] > 0)[0]
                logger.info(f"Weights of topic {category}: \n" + \
                            f"Uids: {positive_score_uid} \n" + \
                            f"Weights: {categories_scores[category][positive_score_uid]}"
                            )
                    
                    
            # Weighted sum of categories
            scores = np.zeros(len(metagraph.hotkeys))
            for category in categories_scores:
                scores += categories_scores[category] * cst.CATEGORIES_WEIGHTS[category]
            
            scores_weights = scores.tolist()

            # Burn
            alpha_burn_weights = [0.0] * len(metagraph.hotkeys)
            owner_hotkey = "5HN1QZq7MyGnutpToCZGdiabP3D339kBjKXfjb1YFaHacdta"
            owner_hotkey_index = metagraph.hotkeys.index(owner_hotkey)
            logger.info(f"🔥 Burn alpha by setting weight for uid {owner_hotkey_index} - {owner_hotkey} (owner's hotkey): 1")
            alpha_burn_weights[owner_hotkey_index] = 1
            
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

            # Wait before next scoring cycle
            await asyncio.sleep(cst.EPOCH_LENGTH)

        except Exception as e:
            logger.error(f"Error in score aggregation: {traceback.format_exc()}")
            await asyncio.sleep(10)  # Backoff on error
            

if __name__=="__main__":
    asyncio.run(main())