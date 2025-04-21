import asyncio
import traceback
from datetime import datetime

import nuance.models as models
from nuance.database import PostRepository, InteractionRepository, SocialAccountRepository, NodeRepository
from nuance.database.engine import get_db_session
from nuance.processing import PipelineFactory
from nuance.social import SocialContentProvider
from nuance.utils.logging import logger


class NuanceValidator:
    def __init__(self, config):
        # Setup components
        self.config = config
        
        # Processing queues
        self.post_queue = asyncio.Queue()
        self.interaction_queue = asyncio.Queue()
        # Scoring queue
        self.scoring_queue = asyncio.Queue()
        
        # Dependency tracking and cache
        self.processed_posts_cache = {}  # In-memory cache for fast lookup
        self.waiting_interactions = {}   # Temporary holding area
        
    async def initialize(self):
        # Initialize components and repositories
        self.social = SocialContentProvider()
        self.pipelines = {
            "post": PipelineFactory.create_post_pipeline(),
            "interaction": PipelineFactory.create_interaction_pipeline()
        }
        self.post_repository = PostRepository(get_db_session)
        self.interaction_repository = InteractionRepository(get_db_session)
        self.account_repository = SocialAccountRepository(get_db_session)
        self.node_repository = NodeRepository(get_db_session)
        
        # Start workers
        self.workers = [
            asyncio.create_task(self.content_discovery()),
            asyncio.create_task(self.post_processor()),
            asyncio.create_task(self.interaction_processor()),
            asyncio.create_task(self.score_aggregator())
        ]
    
    async def content_discovery(self, commit):
        """
        Discover new content with database awareness.
        This method periodically uses the social component (SocialContentProvider) to discover new content
        including commits from miners that pack there social accounts then discovers new posts and interactions for these accounts.
        Found content will be check with database to avoid duplicates then pushed to the processing queues.
        """
        # Main loop
        while True:
            # Get last processed timestamps from DB for this account
            account = await self.account_repository.get_by_platform_and_account_id(
                commit.platform, commit.account_id
            )
        
            last_discovery = account.extra_data.get("last_discovery_timestamp") if account else None
            
            # Discover new content since last time
            content = await self.social.discover_content(commit, since=last_discovery)
            
            # Filter out already processed items
            new_posts = []
            for post in content["posts"]:
                existing = await self.post_repository.get_by_platform_id(
                    commit.platform, post["id"]
                )
                if not existing:
                    new_posts.append(post)
            
            new_interactions = []
            for interaction in content["interactions"]:
                existing = await self.interaction_repository.get_by_platform_id(
                    commit.platform, interaction["id"]
                )
                if not existing:
                    new_interactions.append(interaction)
            
            # Update account's last discovery timestamp
            if account:
                account.extra_data["last_discovery_timestamp"] = datetime.now().isoformat()
                await self.account_repository.update(account)
            
            return {
                "posts": new_posts,
                "interactions": new_interactions
            }
    
    async def post_processor(self):
        """Process posts and save to database."""
        while True:
            post: models.Post = await self.post_queue.get()
            
            try:
                # Process the post
                result = await self.pipelines["post"].process(post)
                
                # Save to database regardless of processing outcome
                post.processing_status = (
                    models.ProcessingStatus.PROCESSED if result.success 
                    else models.ProcessingStatus.REJECTED
                )
                post.processing_note = result.processing_note
                
                saved_post = await self.post_repository.create(post)
                
                if result.success:
                    # Update cache with processed post
                    self.processed_posts_cache[post.platform_id] = saved_post
                    
                    # Process any waiting interactions
                    waiting = self.waiting_interactions.pop(post.platform_id, [])
                    for interaction in waiting:
                        await self.interaction_queue.put(interaction)
            except Exception as e:
                logger.error(f"Error processing post: {traceback.format_exc()}")
            finally:
                self.post_queue.task_done()
    
    async def interaction_processor(self):
        """Process interactions with DB integration."""
        while True:
            raw_interaction = await self.interaction_queue.get()
            
            try:
                parent_post_id = raw_interaction.get("in_reply_to_status_id")
                
                # First check cache for parent post
                parent_post = self.processed_posts_cache.get(parent_post_id)
                
                # If not in cache, try database
                if not parent_post and parent_post_id:
                    parent_post = await self.post_repository.get_by_platform_id(
                        raw_interaction.get("platform"), parent_post_id
                    )
                    # Add to cache if found
                    if parent_post:
                        self.processed_posts_cache[parent_post_id] = parent_post
                
                if parent_post:
                    # Convert to domain model with parent post ID
                    interaction = self.social.platform_adapter.to_interaction(
                        raw_interaction, parent_post.id
                    )
                    
                    # Process the interaction
                    result = await self.pipelines["interaction"].process(interaction)
                    
                    # Save to database
                    interaction.processing_status = (
                        ProcessingStatus.PROCESSED if result.success 
                        else ProcessingStatus.REJECTED
                    )
                    interaction.processing_note = result.processing_note
                    
                    saved_interaction = await self.interaction_repository.create(interaction)
                    
                    if result.success:
                        # Queue for scoring
                        await self.scored_queue.put({
                            "interaction": saved_interaction,
                            "post": parent_post,
                            "miner_hotkey": raw_interaction.get("miner_hotkey")
                        })
                else:
                    # Parent not processed yet, add to waiting list
                    logger.info(f"Interaction waiting for post {parent_post_id}")
                    self.waiting_interactions.setdefault(parent_post_id, []).append(raw_interaction)
            except Exception as e:
                logger.error(f"Error processing interaction: {traceback.format_exc()}")
            finally:
                self.interaction_queue.task_done()
    
    async def score_aggregator(self):
        """Complex scoring with DB support."""
        while True:
            item = await self.scored_queue.get()
            
            try:
                interaction = item["interaction"]
                post = item["post"] 
                miner_hotkey = item["miner_hotkey"]
                
                # Complex scoring logic
                base_score = 1.0
                
                # Factor 1: Interaction type multiplier
                type_multipliers = {
                    "comment": 1.0,
                    "like": 0.5,
                    "retweet": 0.8
                }
                type_score = type_multipliers.get(interaction.interaction_type, 1.0)
                
                # Factor 2: Account influence
                account = await self.account_repository.get_by_id(interaction.account_id)
                influence_score = min(1.0, account.extra_data.get("followers_count", 0) / 10000)
                
                # Calculate final score
                final_score = base_score * type_score * (1 + influence_score)
                
                # Update interaction with score
                interaction.score = final_score
                await self.interaction_repository.update(interaction)
                
                # Update miner scores in DB
                current_block = await self.subtensor.get_current_block()
                
                # Get node by hotkey
                node = await self.node_repository.get_by_hotkey_netuid(miner_hotkey, constants.NETUID)
                if not node:
                    logger.warning(f"Unknown miner: {miner_hotkey}")
                    return
                
                # Structure in node's metadata to track scores
                node.metadata.setdefault("scores", {})
                node.metadata["scores"].setdefault(str(current_block), 0.0)
                node.metadata["scores"][str(current_block)] += final_score
                
                await self.node_repository.update(node)
                
            except Exception as e:
                logger.error(f"Error in scoring: {traceback.format_exc()}")
            finally:
                self.scored_queue.task_done()