import asyncio
import shelve
from types import SimpleNamespace
import traceback
from pathlib import Path

import bittensor as bt
from loguru import logger

from nuance.settings import settings
from nuance.utils.bittensor_utils import get_wallet
from nuance.social.content_provider import SocialContentProvider
from nuance.processing.pipeline import PipelineFactory
from nuance.processing.base import ProcessingResult
# from nuance.chain.interface import ChainInterface
import nuance.chain as chain
import nuance.constants as constants
from nuance.utils.bittensor_utils import get_metagraph, get_wallet, get_subtensor


class NuanceValidator:
    """Main validator class that orchestrates the entire process."""
    
    def __init__(self, config: bt.Config):
        """Initialize the validator."""
        self.config = config
        self.db_path = Path(self.config.validator.fullpath) / "validator.db"
        self.keypair = None
    
    async def initialize(self):
        """Initialize all components and services."""
        logger.info("Initializing validator components...")

        # Create bittensor objects
        self.subtensor = await get_subtensor()
        self.metagraph = await get_metagraph()
        self.wallet = await get_wallet()
        
        if self.wallet.hotkey.ss58_address not in self.metagraph.hotkeys:
            logger.error(
                f"\nYour validator: {self.wallet} is not registered to chain connection: {self.subtensor} \nRun 'btcli register' and try again."
            ) 
            exit()
        else:
            self.uid = self.metagraph.hotkeys.index(self.wallet.hotkey.ss58_address)
            logger.info(f"Running validator on uid: {self.uid}")
        
        
        # Create social content provider
        self.social = SocialContentProvider()
        
        # Create processing pipelines
        self.pipelines = PipelineFactory.create_pipelines(keypair=self.keypair)
        
        logger.info("✅ Validator components initialized successfully")
    
    async def process_commit(self, commit: SimpleNamespace, step_block: int, db: shelve.Shelf):
        """Process a single commit."""
        try:
            # Step 1: Verify account
            logger.info(f"Verifying account {commit.platform}:{commit.account_id} for {commit.hotkey}")
            is_verified, error = await self.social.verify_account(commit)
            if not is_verified:
                logger.warning(f"❌ Account verification failed: {error}")
                return
            
            logger.info(f"✅ Account verified successfully")
            
            # Step 2: Discover new content
            logger.info(f"Discovering new content for {commit.platform}:{commit.account_id}")
            last_seen_id = db.get("last_seen_ids", {}).get(commit.account_id)
            
            content = await self.social.discover_content(commit, last_seen_id)
            posts = content["posts"]
            interactions = content["interactions"]
            
            logger.info(f"📝 Found {len(posts)} new posts")
            logger.info(f"💬 Found {len(interactions)} new interactions")
            
            # Step 3: Process posts
            processed_posts = {}
            for post in posts:
                # Tag with miner info
                post["miner_hotkey"] = commit.hotkey
                
                # Skip if already processed
                post_id = post["id"]
                if post_id in db.get("processed_posts", {}):
                    logger.debug(f"⏩ Post {post_id} already processed")
                    processed_posts[post_id] = db["processed_posts"][post_id]
                    continue
                
                # Process through pipeline
                logger.info(f"Processing post {post_id}")
                result = await self.pipelines["post"].process(post)
                
                # Store result
                db.setdefault("processed_posts", {})[post_id] = post
                processed_posts[post_id] = post
                
                if not result:
                    logger.info(f"🚫 Post {post_id} failed processing: {result.errors}")
                else:
                    logger.info(f"✅ Post {post_id} successfully processed")
            
            # Step 4: Process interactions
            for interaction in interactions:
                # Tag with miner info
                interaction["miner_hotkey"] = commit.hotkey
                
                # Skip if already processed
                interaction_id = interaction["id"]
                if interaction_id in db.get("processed_interactions", set()):
                    logger.debug(f"⏩ Interaction {interaction_id} already processed")
                    continue
                
                # Get parent post if it exists
                parent_id = interaction.get("parent_id")
                if parent_id and parent_id in processed_posts:
                    # Add parent post to interaction for processing
                    interaction["parent_post"] = processed_posts[parent_id]
                    
                    # Process through pipeline
                    logger.info(f"Processing interaction {interaction_id}")
                    result = await self.pipelines["interaction"].process(interaction)
                    
                    # Store result and update scores
                    if result:
                        logger.info(f"✅ Interaction {interaction_id} successfully processed")
                        
                        # Update scores if available
                        if "score" in interaction:
                            score = interaction["score"]
                            logger.info(f"💯 Score for interaction {interaction_id}: {score}")
                            
                            # Add to miner's score for this block
                            db.setdefault("scores", {}).setdefault(commit.hotkey, {}).setdefault(step_block, 0)
                            db["scores"][commit.hotkey][step_block] += score
                    else:
                        logger.info(f"🚫 Interaction {interaction_id} failed processing: {result.errors}")
                
                # Mark as processed
                db.setdefault("processed_interactions", set()).add(interaction_id)
            
            # Update the last seen ID for this account
            all_ids = [p["id"] for p in posts] + [i["id"] for i in interactions]
            if all_ids:
                newest_id = max(all_ids)
                db.setdefault("last_seen_ids", {})[commit.account_id] = newest_id
                
        except Exception as e:
            error_msg = f"❌ Error processing commit {commit.hotkey}: {traceback.format_exc()}"
            logger.error(error_msg)
            db.setdefault("errors", []).append(error_msg)
    
    async def main_loop(self, shutdown_event: asyncio.Event):
        """Main processing loop."""
        # Open database
        with shelve.open(str(self.db_path), writeback=True) as db:
            # Initialize if needed
            db.setdefault("processed_posts", {})
            db.setdefault("processed_interactions", set())
            db.setdefault("scores", {})
            db.setdefault("last_seen_ids", {})
            db.setdefault("errors", [])
            
            while not shutdown_event.is_set():
                try:
                    # Get current block
                    step_block = await self.subtensor.get_current_block()
                    logger.info(f"🔄 Processing block {step_block}")
                    
                    # Get commitments from chain
                    commits = await chain.get_commitments(self.subtensor, self.metagraph, constants.NETUID)
                    logger.info(f"✅ Pulled {len(commits)} commits from chain")
                    
                    # Process each commit
                    for commit in commits.values():
                        await self.process_commit(commit, step_block, db)
                    
                    # Update weights if it's time
                    last_weight_block = db.get("last_weight_block", 0)
                    if step_block - last_weight_block >= settings.EPOCH_LENGTH:
                        # Calculate and set weights
                        weights = self.chain.calculate_weights(db["scores"])
                        await self.chain.set_weights(weights)
                        db["last_weight_block"] = step_block
                        logger.info(f"✅ Updated weights on block {step_block}")
                    
                    # Take a snapshot of the database
                    db_path = Path(str(self.db_path))
                    snapshot_path = str(db_path.with_name(db_path.stem + "_snapshot" + db_path.suffix))
                    with shelve.open(snapshot_path, writeback=False) as snapshot_db:
                        for key in db:
                            snapshot_db[key] = db[key]
                    
                    # Wait for next cycle
                    await asyncio.sleep(settings.POLLING_INTERVAL)
                    
                except Exception as e:
                    error_msg = f"❌ Error in main loop: {traceback.format_exc()}"
                    logger.error(error_msg)
                    db.setdefault("errors", []).append(error_msg)
                    await asyncio.sleep(5)  # Short delay on error
    
    async def run(self):
        """Run the validator."""
        # Initialize components
        await self.initialize()
        
        # Create shutdown event
        shutdown_event = asyncio.Event()
        
        try:
            # Start main loop
            await self.main_loop(shutdown_event)
        except asyncio.CancelledError:
            logger.info("Validator shutdown requested")
            shutdown_event.set()
        except Exception as e:
            logger.error(f"Unhandled exception: {traceback.format_exc()}")
        finally:
            logger.info("Validator shutting down")


async def main():
    """Main entry point."""
    # Parse config
    config = bt.config(bt.subtensor.config())
    config.subtensor.network = "test"  # Default to testnet
    config = bt.subtensor.add_defaults(config)
    
    # Create and run validator
    validator = NuanceValidator(config)
    await validator.run()


if __name__ == "__main__":
    # Configure logging
    logger.add("validator.log", rotation="10 MB")
    
    # Run the validator
    asyncio.run(main())