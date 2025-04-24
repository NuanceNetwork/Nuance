import asyncio
import datetime
import math
import traceback

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

        # Chain components
        self.subtensor = None  # Will be initialized later

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

        # Initialize chain components
        self.subtensor = await get_subtensor()
        self.wallet = await get_wallet()
        self.metagraph = await get_metagraph()

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
                    # First verify the account
                    is_verified, error = await self.social.verify_account(commit)
                    if not is_verified:
                        logger.warning(
                            f"Account {commit.username} is not verified: {error}"
                        )
                        continue

                    # Get last processed timestamps from DB for this account
                    account = await self.account_repository.get_by_platform_id(
                        commit.platform, commit.account_id
                    )

                    # Discover new content since last time
                    content = await self.social.discover_content(commit)

                    # Filter out already processed items
                    new_posts = []
                    for post_data in content["posts"]:
                        existing = await self.post_repository.get_by_platform_id(
                            commit.platform, post_data["id"]
                        )
                        if not existing:
                            new_posts.append(post_data)

                    new_interactions = []
                    for interaction_data in content["interactions"]:
                        existing = await self.interaction_repository.get_by_platform_id(
                            commit.platform, interaction_data["id"]
                        )
                        if not existing:
                            new_interactions.append(interaction_data)

                    # Queue new content for processing
                    for post in new_posts:
                        await self.post_queue.put(post)

                    for interaction_data in new_interactions:
                        await self.interaction_queue.put(interaction_data)

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

            try:
                logger.info(
                    f"Processing post: {post.post_id} from {post.account_id} on platform {post.platform_type}"
                )

                # Process the post
                result: ProcessingResult = await self.pipelines["post"].process(post)

                # Save to database regardless of processing outcome
                post.processing_status = result.status
                post.processing_note = result.processing_note

                saved_post = await self.post_repository.create(post)

                if result.status == models.ProcessingStatus.ACCEPTED:
                    logger.info(f"Post {post.post_id} processed successfully")
                    # Update cache with processed post
                    self.processed_posts_cache[post.post_id] = saved_post

                    # Process any waiting interactions
                    waiting = self.waiting_interactions.pop(post.post_id, [])
                    if waiting:
                        logger.info(
                            f"Processing {len(waiting)} waiting interactions for post {post.post_id}"
                        )
                        for interaction in waiting:
                            await self.interaction_queue.put(interaction)
                else:
                    logger.info(
                        f"Post {post.post_id} rejected: {result.processing_note}"
                    )
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

            try:
                parent_post_id = interaction.post_id
                platform = interaction.platform_type

                logger.info(
                    f"Processing interaction {interaction.interaction_id} for post {parent_post_id}"
                )

                # First check cache for parent post
                parent_post = self.processed_posts_cache.get(parent_post_id)

                # If not in cache, try database
                if not parent_post and parent_post_id:
                    parent_post = await self.post_repository.get_by_platform_id(
                        platform, parent_post_id
                    )
                    # Add to cache if found
                    if parent_post:
                        self.processed_posts_cache[parent_post_id] = parent_post

                if parent_post:
                    # Process the interaction
                    from nuance.processing.sentiment import InteractionPostContext
                    result: ProcessingResult = await self.pipelines["interaction"].process(
                        input_data=InteractionPostContext(
                            interaction=interaction,
                            parent_post=parent_post,
                        )
                    )

                    # Save to database
                    interaction.processing_status = result.status
                    interaction.processing_note = result.processing_note

                    saved_interaction = await self.interaction_repository.create(
                        interaction
                    )

                    if result.status == models.ProcessingStatus.ACCEPTED:
                        logger.info(
                            f"Interaction {interaction.interaction_id} processed successfully"
                        )
                    else:
                        logger.info(
                            f"Interaction {interaction.interaction_id} rejected: {result.processing_note}"
                        )
                else:
                    # Parent not processed yet, add to waiting list
                    logger.info(
                        f"Interaction {interaction.interaction_id} waiting for post {parent_post_id}"
                    )
                    self.waiting_interactions.setdefault(parent_post_id, []).append(
                        interaction
                    )
            except Exception as e:
                logger.error(f"Error processing interaction: {traceback.format_exc()}")
            finally:
                self.interaction_queue.task_done()

    async def score_aggregating(self):
        """
        Calculate scores for all nodes based on recent interactions.
        This method periodically queries for interactions from the last 7 days,
        scores them based on freshness and account influence, and updates node scores.
        """
        while True:
            try:
                # Get current block for score tracking
                current_block = await self.subtensor.get_current_block()
                logger.info(f"Calculating scores for block {current_block}")

                # Get cutoff date (7 days ago)
                cutoff_date = datetime.datetime.now(
                    tz=datetime.timezone.utc
                ) - datetime.timedelta(days=7)

                # 1. Get all interactions from the last 7 days that are PROCESSED
                recent_interactions = (
                    await self.interaction_repository.get_recent_interactions(
                        since_date=cutoff_date
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
                node_scores = {}

                for interaction in recent_interactions:
                    try:
                        # Get the post being interacted with
                        post = await self.post_repository.get_by_platform_id(
                            interaction.platform_type, interaction.post_id
                        )
                        if not post:
                            logger.warning(
                                f"Post not found for interaction {interaction.interaction_id}"
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
                            post_account.node_hotkey, constants.NETUID
                        )
                        if not node:
                            logger.warning(
                                f"Node not found for account {post_account.account_id}"
                            )
                            continue

                        # Get node (miner) for scoring
                        miner_hotkey = node.hotkey

                        # Calculate score for this interaction
                        score = self._calculate_interaction_score(
                            interaction=interaction,
                            cutoff_date=cutoff_date,
                        )

                        # Add to node's score
                        if score > 0:
                            if miner_hotkey not in node_scores:
                                node_scores[miner_hotkey] = 0.0
                            node_scores[miner_hotkey] += score

                    except Exception as e:
                        logger.error(
                            f"Error scoring interaction {interaction.interaction_id}: {traceback.format_exc()}"
                        )

                # 3. Set weights for all nodes
                weights = [0.0] * len(self.metagraph.hotkeys)
                for hotkey, score in node_scores.items():
                    if hotkey in self.metagraph.hotkeys:
                        weights[self.metagraph.hotkeys.index(hotkey)] = score
                        
                # 4. Update metagraph with new weights
                await self.subtensor.set_weights(
                    wallet=self.wallet,
                    netuid=constants.NETUID,
                    uids=list(range(len(weights))),
                    weights=weights,
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
    ) -> float:
        """
        Calculate score for an interaction based on type, recency, and account influence.

        Args:
            interaction: The interaction to score
            interaction_account: The account that made the interaction
            cutoff_date: The date beyond which interactions are not scored (7 days ago)

        Returns:
            float: The calculated score
        """
        # Skip if the interaction is too old
        if interaction.created_at < cutoff_date:
            return 0.0

        type_weights = {
            models.InteractionType.REPLY: 1.0,
        }

        base_score = type_weights.get(interaction.interaction_type, 0.5)

        # Recency factor - newer interactions get higher scores
        now = datetime.datetime.now(tz=datetime.timezone.utc)
        age_days = (now - interaction.created_at).days
        max_age = 7  # Max age in days

        # Linear decay from 1.0 (today) to 0.3 (7 days old)
        recency_factor = 1.0 - (0.7 * age_days / max_age)

        # Account influence factor (based on followers)
        followers = interaction.social_account.extra_data.get("followers_count", 0)
        influence_factor = min(1.0, followers / 10000)  # Cap at 1.0
        
        # Bonus score for topics
        topics = interaction.post.topics
        if topics and len(topics) > 0:
            topic_factor = 2
            
        # Calculate final score
        final_score = base_score * recency_factor * math.log(1 + influence_factor) * topic_factor

        return final_score

if __name__ == "__main__":
    validator = NuanceValidator()
    loop = asyncio.get_event_loop()
    loop.run_until_complete(validator.initialize())
    loop.run_forever()
