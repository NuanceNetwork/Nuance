# neurons/validator/main.py
import asyncio
import datetime
import json
import traceback
import re

import bittensor as bt
import numpy as np
import uvicorn

import nuance.constants as cst
from nuance.chain import get_commitments
from nuance.database.engine import get_db_session
from nuance.database import (
    PostRepository,
    InteractionRepository,
    SocialAccountRepository,
    NodeRepository,
)
import nuance.models as models
from nuance.constitution import constitution_store
from nuance.processing import ProcessingResult, PipelineFactory
from nuance.social import SocialContentProvider
from nuance.utils.logging import logger
from nuance.utils.bittensor_utils import (
    get_subtensor,
    get_wallet,
    get_metagraph,
    serve_axon_extrinsic,
)
from nuance.settings import settings

from neurons.validator.scoring import ScoreCalculator
from neurons.validator.submission_server.app import create_submission_app


class NuanceValidator:
    def __init__(self):
        # Processing queues
        self.post_queue = asyncio.Queue()
        self.interaction_queue = asyncio.Queue()
        self.submission_queue = asyncio.Queue()

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

        self.score_calculator = ScoreCalculator()

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

        # Initialize submission server
        self.submission_app = create_submission_app(
            submission_queue=self.submission_queue
        )
        config = uvicorn.Config(
            app=self.submission_app,
            host=settings.SUBMISSION_SERVER_HOST,
            port=settings.SUBMISSION_SERVER_PORT,
            loop="none",
        )
        self.submission_server = uvicorn.Server(config)
        # Post IP to chain with bittensor 's serving axon
        await serve_axon_extrinsic(
            subtensor=self.subtensor,
            wallet=self.wallet,
            netuid=settings.NETUID,
            external_port=settings.SUBMISSION_SERVER_EXTERNAL_PORT,
            external_ip=settings.SUBMISSION_SERVER_PUBLIC_IP,
        )

        # Start workers
        self.workers = [
            asyncio.create_task(self.submission_server.serve()),
            asyncio.create_task(self.process_submissions()),
            # asyncio.create_task(self.content_discovering()),
            asyncio.create_task(self.post_processing()),
            asyncio.create_task(self.interaction_processing()),
            asyncio.create_task(self.score_aggregating()),
        ]

        logger.info("Validator initialized successfully")

    async def process_submissions(self):
        while True:
            try:
                # Get submission from queue
                submission_data = await self.submission_queue.get()

                node_hotkey = submission_data.get("hotkey")
                platform = submission_data.get("platform")
                account_id = submission_data.get("account_id")
                username = submission_data.get("username")
                verification_post_id = submission_data.get("verification_post_id")
                post_id = submission_data.get("post_id")
                interaction_id = submission_data.get("interaction_id")
                uuid = submission_data.get("uuid")
                from_gossip = submission_data.get("from_gossip", False)

                logger.info(
                    f"Processing submission from {node_hotkey} (UUID: {uuid}, "
                    f"gossip: {from_gossip}, account: {account_id})"
                )

                # Verify node exists in metagraph
                if node_hotkey not in self.metagraph.hotkeys:
                    logger.warning(f"Node {node_hotkey} not in metagraph, skipping")
                    continue

                # Create/update node
                node = models.Node(node_hotkey=node_hotkey, node_netuid=settings.NETUID)
                await self.node_repository.upsert(node)

                # Verify the account
                account = None
                account_verified = False
                if verification_post_id:
                    node_uid = self.metagraph.hotkeys.index(node_hotkey)
                    commit = models.Commit(
                        uid=node_uid,
                        node_hotkey=node_hotkey,
                        node_netuid=settings.NETUID,
                        platform=platform,
                        account_id=account_id if account_id else None,
                        username=username if username else None,
                        verification_post_id=verification_post_id,
                    )
                    account, error = await self.social.verify_account(commit, node)
                    if not account:
                        logger.warning(
                            f"Account {commit.username} is not verified: {error}"
                        )
                        continue

                    account_verified = True
                    # Upsert account to database
                    await self.account_repository.upsert(account)

                # Process post if provided
                if post_id:
                    # If account is verified
                    if account_verified:
                        existing_post = await self.post_repository.get_by(
                            platform_type=platform, post_id=post_id
                        )

                        if not existing_post:
                            # Fetch post using social provider
                            post = await self.social.get_post(platform, post_id)

                            if not post:
                                logger.warning(
                                    f"Could not fetch post {post_id}, skipping this"
                                )
                                continue
                        else:
                            logger.debug(f"Post {post_id} already exists")
                            post = existing_post
                            post.social_account = (
                                await self.account_repository.get_by_platform_id(
                                    platform_type=post.platform_type,
                                    account_id=post.account_id,
                                )
                            )
                            post = await self.social.get_post(platform, post_id)

                        # Check if post is from verified account
                        if (
                            post.platform_type == account.platform_type
                            and post.account_id == account.account_id
                        ):
                            # Post is from verified account, proceed normally
                            logger.debug(
                                f"Post {post_id} is from verified account {account.account_id}"
                            )
                        else:
                            # Post is from different account - verify ownership claim
                            logger.info(
                                f"Post {post_id} is from different account ({post.account_id}) "
                                f"than verified account ({account.account_id}). Verifying ownership claim."
                            )

                            # Check if verification account username appears as hashtag
                            HASHTAG_PATTERN = re.compile(r"#([A-Za-z0-9_]{1,15})")
                            def extract_hashtags(text: str) -> list[str]:
                                """Extract all valid hashtags from text according to Twitter username rules and hashtag rules."""
                                return [tag.lower() for tag in HASHTAG_PATTERN.findall(text or "")]
                            
                            hashtags = extract_hashtags(post.content)
                            if not account.account_username:
                                logger.warning(
                                    f"Verified account {account.account_id} has no username set, "
                                    f"cannot verify post {post_id}"
                                )
                                continue

                            if account.account_username.lower() not in hashtags:
                                logger.warning(
                                    f"Verified account {account.account_id} cannot claim ownership "
                                    f"of post {post_id}: verification hashtag #{account.account_username} "
                                    f"not found in post content"
                                )
                                continue

                            # Verified account can claim this post - assign post's social account to hotkey
                            post_social_account = post.social_account
                            post_social_account.node_hotkey = account.node_hotkey
                            post_social_account.node_netuid = account.node_netuid
                            await self.account_repository.upsert(post_social_account)

                            logger.info(
                                f"Verified account {account.account_id} successfully claimed "
                                f"ownership of post {post_id} from account {post_social_account.account_id} "
                                f"via hashtag verification"
                            )
                    # If account is not verified, we verify the post itself and claim node 's ownership to the account
                    else:
                        if node_hotkey not in self.metagraph.hotkeys:
                            continue
                        node = models.Node(
                            node_hotkey=node_hotkey, node_netuid=settings.NETUID
                        )
                        post, error = await self.social.verifiy_post(
                            post_id, platform, node
                        )

                        if not post:
                            logger.warning(
                                f"Post {post_id} on platforn {platform} is not verified: {error}"
                            )
                            continue

                        account_verified = True
                        account = post.social_account
                        # Upsert account to database
                        await self.account_repository.upsert(account)

                    # Queue post for processing
                    await self.post_queue.put(post)
                    logger.info(f"Queued post {post_id} for processing")

                # Process interaction if provided (requires post_id)
                if interaction_id:
                    # Double-check post_id exists (should be validated already)
                    if not post_id:
                        logger.error(
                            f"Interaction {interaction_id} submitted without post_id"
                        )
                        continue

                    existing_interaction = await self.interaction_repository.get_by(
                        platform_type=platform, interaction_id=interaction_id
                    )

                    if not existing_interaction:
                        # Use the get_interaction API
                        interaction = await self.social.get_interaction(
                            platform, interaction_id
                        )

                        if interaction:
                            # Verify the interaction is to the submitted post
                            if interaction.post_id != post_id:
                                logger.warning(
                                    f"Interaction {interaction_id} is not to post {post_id}, "
                                    f"actual parent: {interaction.post_id}"
                                )
                                continue

                            # Queue for processing
                            await self.interaction_queue.put(interaction)
                            logger.info(
                                f"Queued interaction {interaction_id} "
                                f"({interaction.interaction_type}) to post {post_id}"
                            )
                        else:
                            logger.warning(
                                f"Could not fetch interaction {interaction_id}"
                            )
                    else:
                        logger.debug(f"Interaction {interaction_id} already exists")

            except Exception:
                logger.error(f"Error processing submission: {traceback.format_exc()}")
                await asyncio.sleep(1)  # Brief pause on error

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
                            platform_type=post.platform_type, post_id=post.post_id
                        )
                        if not existing:
                            new_posts.append(post)

                    new_interactions = []
                    for interaction in discovered_content["interactions"]:
                        existing = await self.interaction_repository.get_by(
                            platform_type=interaction.platform_type,
                            interaction_id=interaction.interaction_id,
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
                await asyncio.sleep(cst.EPOCH_LENGTH)

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
                    logger.info(
                        f"Post {post.post_id} processed successfully with status {result.status}"
                    )
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
                        platform_type=platform_type, post_id=post_id
                    )
                    # Add to cache if found
                    if parent_post:
                        self.processed_posts_cache[post_id] = parent_post

                if (
                    parent_post
                    and parent_post.processing_status
                    == models.ProcessingStatus.ACCEPTED
                ):
                    # Process the interaction
                    from nuance.processing.sentiment import InteractionPostContext

                    result: ProcessingResult = await self.pipelines[
                        "interaction"
                    ].process(
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
                        await self.account_repository.upsert(
                            interaction.social_account, exclude_none_updates=True
                        )

                        # Upsert the interaction to database
                        await self.interaction_repository.upsert(interaction)
                    else:
                        logger.info(
                            f"Interaction {interaction.interaction_id} errored in processing: {result.processing_note}, put back in queue"
                        )
                        await self.interaction_queue.put(interaction)
                elif (
                    parent_post
                    and parent_post.processing_status
                    == models.ProcessingStatus.REJECTED
                ):
                    logger.info(
                        f"Post {post_id} rejected in processing: {parent_post.processing_note}, rejecting interaction {interaction.interaction_id}"
                    )

                    interaction.processing_status = models.ProcessingStatus.REJECTED
                    interaction.processing_note = "Parent post rejected"

                    # Upsert the interacted account to database
                    await self.account_repository.upsert(
                        interaction.social_account, exclude_none_updates=True
                    )

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
        This method periodically queries for interactions from the last SCORING_WINDOW days,
        scores them based on freshness and account influence, and updates node scores.
        """
        while True:
            try:
                # Get current block for score tracking
                current_block = await self.subtensor.get_current_block()
                logger.info(f"Calculating scores for block {current_block}")

                # Get cutoff date
                cutoff_date = datetime.datetime.now(
                    tz=datetime.timezone.utc
                ) - datetime.timedelta(days=cst.SCORING_WINDOW)

                # Get constitution config
                constitution_config = await constitution_store.get_constitution_config()
                constitution_topics = constitution_config.get("topics", {})

                # 1. Get all posts and interactions from the last SCORING_WINDOW days that are PROCESSED and ACCEPTED
                recent_interactions = (
                    await self.interaction_repository.get_recent_interactions(
                        cutoff_date=cutoff_date,
                        processing_status=models.ProcessingStatus.ACCEPTED,
                    )
                )

                if not recent_interactions:
                    logger.info("No recent interactions found for scoring")

                logger.info(
                    f"Found {len(recent_interactions)} recent interactions for scoring"
                )

                recent_posts = await self.post_repository.get_recent_posts(
                    cutoff_date=cutoff_date,
                    processing_status=models.ProcessingStatus.ACCEPTED,
                )

                if not recent_posts:
                    logger.info("No recent posts found for scoring")

                logger.info(f"Found {len(recent_posts)} recent posts for scoring")

                # 2. Calculate scores for all miners (use ScoreCalculator)
                node_scores = await self.score_calculator.calculate_aggregated_scores(
                    recent_posts=recent_posts,
                    recent_interactions=recent_interactions,
                    cutoff_date=cutoff_date,
                    post_repository=self.post_repository,
                    account_repository=self.account_repository,
                    node_repository=self.node_repository,
                )

                # 3. Set weights for all nodes
                owner_hotkey = self.metagraph.owner_hotkey
                owner_hotkey_index = self.metagraph.hotkeys.index(owner_hotkey)

                # We create a score array for each category
                categories_scores = {
                    category: np.zeros(len(self.metagraph.hotkeys))
                    for category in list(constitution_topics.keys())
                }
                for hotkey, scores in node_scores.items():
                    if hotkey in self.metagraph.hotkeys:
                        for category, score in scores.items():
                            if category in categories_scores:
                                categories_scores[category][
                                    self.metagraph.hotkeys.index(hotkey)
                                ] = score

                # Normalize scores for each category
                for category in categories_scores:
                    categories_scores[category] = np.nan_to_num(
                        categories_scores[category], 0
                    )
                    if np.sum(categories_scores[category]) > 0:
                        categories_scores[category] = categories_scores[
                            category
                        ] / np.sum(categories_scores[category])
                    else:
                        # If category has no score (no interaction) then we burn
                        categories_scores[category] = np.zeros_like(
                            categories_scores[category]
                        )
                        categories_scores[category][owner_hotkey_index] = 1.0

                    positive_score_uid = np.where(categories_scores[category] > 0)[0]
                    logger.info(
                        f"Weights of topic {category}: \n"
                        + f"Uids: {positive_score_uid} \n"
                        + f"Weights: {categories_scores[category][positive_score_uid]}"
                    )

                # Weighted sum of categories
                scores = np.zeros(len(self.metagraph.hotkeys))
                for category in categories_scores:
                    scores += categories_scores[category] * constitution_topics.get(
                        category, {}
                    ).get("weight", 0.0)

                scores_weights = scores.tolist()

                # Burn
                alpha_burn_weights = [0.0] * len(self.metagraph.hotkeys)
                logger.info(
                    f"🔥 Burn alpha by setting weight for uid {owner_hotkey_index} - {owner_hotkey} (owner's hotkey): 1"
                )
                alpha_burn_weights[owner_hotkey_index] = 1

                # Combine weights
                combined_weights = [
                    (cst.ALPHA_BURN_RATIO * alpha_burn_weight)
                    + ((1 - cst.ALPHA_BURN_RATIO) * score_weight)
                    for alpha_burn_weight, score_weight in zip(
                        alpha_burn_weights, scores_weights
                    )
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
                await asyncio.sleep(cst.EPOCH_LENGTH)

            except Exception:
                logger.error(f"Error in score aggregation: {traceback.format_exc()}")
                await asyncio.sleep(10)  # Backoff on error


if __name__ == "__main__":
    validator = NuanceValidator()
    loop = asyncio.get_event_loop()
    loop.run_until_complete(validator.initialize())
    loop.run_forever()
