# neurons/validator/main.py
import asyncio
import datetime
from typing import Optional
import json
import math
import traceback

import bittensor as bt
import numpy as np

import nuance.constants as constants
from nuance.chain import get_commitments
from nuance.database.engine import get_db_session
from nuance.database import (
    PostRepository,
    InteractionRepository,
    SocialAccountRepository,
    NodeRepository,
)
import nuance.models as models
from nuance.processing import ProcessingResult, PipelineFactory
from nuance.social import SocialContentProvider
from nuance.utils.logging import logger
from nuance.utils.bittensor_utils import get_subtensor, get_wallet, get_metagraph
from nuance.settings import settings


class NuanceValidator:
    def __init__(self):
        # Processing queues
        self.post_queue = asyncio.Queue()
        self.interaction_queue = asyncio.Queue()

        # Dependency tracking and cache
        self.processed_posts_cache = {}  # In-memory cache for fast lookup
        self.waiting_interactions = {}  # Temporary holding area

        # Bittensor objects
        self.subtensor: bt.AsyncSubtensor = None  # Will be initialized later
        self.wallet: bt.Wallet = None  # Will be initialized later
        self.metagraph: bt.Metagraph = None  # Will be initialized later

    async def initialize(self):
        # Initialize components and repositories
        self.social = SocialContentProvider()
        self.pipelines = {
            "post": PipelineFactory.create_post_pipeline(),
            "interaction": PipelineFactory.create_interaction_pipeline(),
        }
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
            asyncio.create_task(self.content_discovering()),
            asyncio.create_task(self.post_processing()),
            asyncio.create_task(self.interaction_processing()),
            asyncio.create_task(self.score_aggregating()),
        ]

        logger.info("Validator initialized successfully")

    async def content_discovering(self):
        """
        Discover new content with database awareness.
        This method periodically uses the social component (SocialContentProvider) to discover new content
        including commits from miners that pack there social accounts then discovers new posts and interactions for these accounts.
        Found content will be check with database to avoid duplicates then pushed to the processing queues.
        """
        while True:
            try:
                # Get commits from chain
                commits: dict[str, models.Commit] = await get_commitments(
                    self.subtensor, self.metagraph, settings.NETUID
                )
                logger.info(f"✅ Pulled {len(commits)} commits.")

                for hotkey, commit in commits.items():
                    node = models.Node(
                        node_hotkey=commit.node_hotkey,
                        node_netuid=commit.node_netuid,
                    )
                    # Upsert node to database
                    await self.node_repository.upsert(node)
                    
                    # First verify the account
                    account, error = await self.social.verify_account(commit, node)
                    if not account:
                        logger.warning(
                            f"Account {commit.username} is not verified: {error}"
                        )
                        continue
                    
                    # Upsert account to database
                    await self.account_repository.upsert(account)

                    # Discover new content
                    discovered_content = await self.social.discover_contents(account)

                    # Filter out already processed items
                    new_posts = []
                    for post in discovered_content["posts"]:
                        existing = await self.post_repository.get_by(
                            platform_type=post.platform_type,
                            post_id=post.post_id
                        )
                        if not existing:
                            new_posts.append(post)

                    new_interactions = []
                    for interaction in discovered_content["interactions"]:
                        existing = await self.interaction_repository.get_by(
                            platform_type=interaction.platform_type,
                            interaction_id=interaction.interaction_id
                        )
                        if not existing:
                            new_interactions.append(interaction)

                    # Queue new content for processing
                    for post in new_posts:
                        await self.post_queue.put(post)

                    for interaction in new_interactions:
                        await self.interaction_queue.put(interaction)

                    logger.info(
                        f"Queued {len(new_posts)} posts and {len(new_interactions)} interactions for {commit.account_id}"
                    )

                # Sleep before next discovery cycle
                await asyncio.sleep(constants.EPOCH_LENGTH)

            except Exception:
                logger.error(f"Error in content discovery: {traceback.format_exc()}")
                await asyncio.sleep(10)  # Backoff on error

    async def post_processing(self):
        """
        Process posts with DB integration.
        This method constantly checks the post queue for new posts and processes them.
        It will then save the post to the database and update the cache.
        """
        while True:
            post: models.Post = await self.post_queue.get()

            # TODO: Make this a task to handle multiple posts in concurrent, be careful with concurrency on cache writes
            try:
                logger.info(
                    f"Processing post: {post.post_id} from {post.account_id} on platform {post.platform_type}"
                )

                # Process the post
                result: ProcessingResult = await self.pipelines["post"].process(post)
                post: models.Post = result.output
                post.processing_status = result.status
                post.processing_note = json.dumps(result.details)

                if result.status != models.ProcessingStatus.ERROR:
                    logger.info(f"Post {post.post_id} processed successfully with status {result.status}")
                    # Upsert post to database
                    await self.post_repository.upsert(post)
                    # Update cache with processed post
                    self.processed_posts_cache[post.post_id] = post

                    # Process any waiting interactions
                    waitings = self.waiting_interactions.pop(post.post_id, [])
                    if waitings:
                        logger.info(
                            f"Processing {len(waitings)} waiting interactions for post {post.post_id}"
                        )
                        for interaction in waitings:
                            await self.interaction_queue.put(interaction)
                else:
                    logger.info(
                        f"Post {post.post_id} errored in processing: {result.processing_note}, put back in queue"
                    )
                    await self.post_queue.put(post)
            except Exception as e:
                logger.error(f"Error processing post: {traceback.format_exc()}")
            finally:
                self.post_queue.task_done()

    async def interaction_processing(self):
        """
        Process interactions with DB integration.
        This method constantly checks the interaction queue for new interactions and processes them, making sure that the parent post is already processed,
        if not it will add the interaction to the waiting list and try again later.
        It will then save the interaction to the database and update the cache.
        """
        while True:
            interaction: models.Interaction = await self.interaction_queue.get()

            # TODO: Make this a task to handle multiple interactions in concurrent, be careful with concurrency on cache writes
            try:
                platform_type = interaction.platform_type
                account_id = interaction.account_id
                post_id = interaction.post_id

                logger.info(
                    f"Processing interaction {interaction.interaction_id} from {account_id} to post {post_id} on platform {platform_type}"
                )

                # First check cache for parent post
                parent_post = self.processed_posts_cache.get(post_id)

                # If not in cache, try database
                if not parent_post and post_id:
                    parent_post = await self.post_repository.get_by(
                        platform_type=platform_type,
                        post_id=post_id
                    )
                    # Add to cache if found
                    if parent_post:
                        self.processed_posts_cache[post_id] = parent_post

                if parent_post and parent_post.processing_status == models.ProcessingStatus.ACCEPTED:
                    # Process the interaction
                    from nuance.processing.sentiment import InteractionPostContext
                    result: ProcessingResult = await self.pipelines["interaction"].process(
                        input_data=InteractionPostContext(
                            interaction=interaction,
                            parent_post=parent_post,
                        )
                    )
                    interaction: models.Interaction = result.output
                    interaction.processing_status = result.status
                    interaction.processing_note = json.dumps(result.details)

                    if result.status != models.ProcessingStatus.ERROR:
                        logger.info(
                            f"Interaction {interaction.interaction_id} processed successfully with status {result.status}"
                        )
                        # Upsert the interacted account to database
                        await self.account_repository.upsert(interaction.social_account)

                        # Upsert the interaction to database
                        await self.interaction_repository.upsert(interaction)
                    else:
                        logger.info(
                            f"Interaction {interaction.interaction_id} errored in processing: {result.processing_note}, put back in queue"
                        )
                        await self.interaction_queue.put(interaction)
                elif parent_post and parent_post.processing_status == models.ProcessingStatus.REJECTED:
                    logger.info(
                        f"Post {post_id} rejected in processing: {parent_post.processing_note}, rejecting interaction {interaction.interaction_id}"
                    )
                    
                    interaction.processing_status = models.ProcessingStatus.REJECTED
                    interaction.processing_note = "Parent post rejected"
                    
                    # Upsert the interacted account to database
                    await self.account_repository.upsert(interaction.social_account)
                    
                    # Upsert the interaction to database
                    await self.interaction_repository.upsert(interaction)
                    
                else:
                    # Parent not processed yet, add to waiting list
                    logger.info(
                        f"Interaction {interaction.interaction_id} waiting for post {post_id}"
                    )
                    self.waiting_interactions.setdefault(post_id, []).append(
                        interaction
                    )
            except Exception as e:
                logger.error(f"Error processing interaction: {traceback.format_exc()}")
            finally:
                self.interaction_queue.task_done()

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

                # 1. Get all interactions from the last 14 days that are PROCESSED and ACCEPTED
                recent_interactions = (
                    await self.interaction_repository.get_recent_interactions(
                        cutoff_date=cutoff_date,
                        processing_status=models.ProcessingStatus.ACCEPTED
                    )
                )

                if not recent_interactions:
                    logger.info("No recent interactions found for scoring")
                    await asyncio.sleep(constants.EPOCH_LENGTH)
                    continue

                logger.info(
                    f"Found {len(recent_interactions)} recent interactions for scoring"
                )

                # 2. Calculate scores for all miners (keyed by hotkey)
                node_scores: dict[str, dict[str, float]] = {} # {hotkey: {category: score}}

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
                            f"Error scoring interaction {interaction.interaction_id}: {traceback.format_exc()}"
                        )

                # 3. Set weights for all nodes
                # We create a score array for each category
                categories_scores = {category: np.zeros(len(self.metagraph.hotkeys)) for category in list(constants.CATEGORIES_WEIGHTS.keys())}
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
                    scores += categories_scores[category] * constants.CATEGORIES_WEIGHTS[category]
                
                scores_weights = scores.tolist()

                # Burn
                alpha_burn_weights = [0.0] * len(self.metagraph.hotkeys)
                owner_hotkey = "5HN1QZq7MyGnutpToCZGdiabP3D339kBjKXfjb1YFaHacdta"
                owner_hotkey_index = self.metagraph.hotkeys.index(owner_hotkey)
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
                await self.subtensor.set_weights(
                    wallet=self.wallet,
                    netuid=settings.NETUID,
                    uids=list(range(len(combined_weights))),
                    weights=combined_weights,
                )
                logger.info(f"✅ Updated weights on block {current_block}.")

                # Wait before next scoring cycle
                await asyncio.sleep(constants.EPOCH_LENGTH)

            except Exception as e:
                logger.error(f"Error in score aggregation: {traceback.format_exc()}")
                await asyncio.sleep(10)  # Backoff on error

    def _calculate_interaction_score(
        self,
        interaction: models.Interaction,
        cutoff_date: datetime.datetime,
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
        interaction.created_at = interaction.created_at.replace(tzinfo=datetime.timezone.utc)
        # Skip if the interaction is too old
        if interaction.created_at < cutoff_date:
            return None

        type_weights = {
            models.InteractionType.REPLY: 1.0,
        }

        base_score = type_weights.get(interaction.interaction_type, 0.5)

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
            interaction_scores: dict[str, float] = {"else": score}
        else:
            interaction_scores: dict[str, float] = {
                topic: score for topic in post_topics
            }
        
        return interaction_scores

if __name__ == "__main__":
    validator = NuanceValidator()
    loop = asyncio.get_event_loop()
    loop.run_until_complete(validator.initialize())
    loop.run_forever()
