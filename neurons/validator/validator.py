import os
import sys
import asyncio
from collections import defaultdict
from pathlib import Path
import shelve
import traceback

import bittensor as bt
from loguru import logger

from neurons.config import get_config
from neurons.validator.api_server import run_api_server
import nuance.constants as constants
import nuance.chain as chain
import nuance.twitter as twitter
from nuance.utils import record_db_error

class Validator:
    def __init__(self, config: bt.Config):
        self.config = config
        
    def setup_logging(self):
        # Remove default loguru handler
        logger.remove()
        
        # Get log level from config
        log_level = "INFO"
        if self.config.logging.trace:
            log_level = "TRACE"
        elif self.config.logging.debug:
            log_level = "DEBUG"
        elif self.config.logging.warning:
            log_level = "WARNING"
        elif self.config.logging.error:
            log_level = "ERROR"
        elif self.config.logging.critical:
            log_level = "CRITICAL"

        # Console log
        logger.add(sys.stderr, level=log_level)
        # File log
        logger.add(os.path.join(self.config.neuron.fullpath, "logfile.log"), level=log_level, rotation="10 MB", retention="10 days", compression="zip")

        # Print information to the logs
        logger.info(f"Running validator for subnet: {self.config.netuid} on network: {self.config.subtensor.network} with config:")
        logger.info(self.config)
        
    async def setup_bittensor_objects(self):
        logger.info("Setting up Bittensor objects.")
        self.wallet = bt.wallet(config=self.config)
        logger.info(f"Wallet: {self.wallet}")
        self.subtensor = bt.async_subtensor(config=self.config)
        await self.subtensor.initialize()
        self.metagraph = await self.subtensor.metagraph(self.config.netuid)
        logger.info(f"Metagraph: {self.metagraph}")

        if self.wallet.hotkey.ss58_address not in self.metagraph.hotkeys:
            logger.error(
                f"\nYour validator: {self.wallet} is not registered to chain connection: {self.subtensor} \nRun 'btcli register' and try again."
            )
            exit()
        else:
            self.uid = self.metagraph.hotkeys.index(self.wallet.hotkey.ss58_address)
            logger.info(f"Running validator on uid: {self.uid}")
            
    async def main_loop(self, shutdown_event: asyncio.Event) -> None:
        """
        Main async loop:
        - Processes tweet replies.
        - Computes EMA-based weights.
        - Updates blockchain weights.
        """
        with shelve.open(self.config.validator.db_filename, writeback=True) as db:
            scores = defaultdict(dict)
            db.setdefault("scores", scores)
            db.setdefault("step_blocks", [])
            db.setdefault("total_seen", 0)
            db.setdefault("last_set_weights", 0)
            db.setdefault("seen", set())
            db.setdefault("parent_tweets", {})
            db.setdefault("child_replies", [])
            db.setdefault("errors", [])

            while not shutdown_event.is_set():
                db_path = Path(self.config.validator.db_filename)
                snapshot_db_path = str(db_path.with_name(db_path.stem + "_snapshot" + db_path.suffix))
                with shelve.open(snapshot_db_path, writeback=False) as snapshot_db:
                    snapshot_db["scores"] = db["scores"]
                    snapshot_db["step_blocks"] = db["step_blocks"]
                    snapshot_db["total_seen"] = db["total_seen"]
                    snapshot_db["last_set_weights"] = db["last_set_weights"]
                    snapshot_db["seen"] = db["seen"]
                    snapshot_db["parent_tweets"] = db["parent_tweets"]
                    snapshot_db["child_replies"] = db["child_replies"]
                    snapshot_db["errors"] = db["errors"]

                try:
                    step_block = await self.subtensor.get_current_block()
                    db["step_blocks"].append(step_block)
                    logger.info(f"🔄 Processing block {step_block}.")

                    commits = await chain.get_commitments(
                        subtensor=self.subtensor, metagraph=self.metagraph, netuid=self.config.netuid
                    )
                    logger.info(f"✅ Pulled {len(commits)} commits.")

                    for commit in commits.values():
                        try:
                            replies = await twitter.get_all_replies(commit.account_id)
                            logger.info(
                                f"💬 Found {len(replies)} replies for account {commit.account_id}."
                            )
                            tasks = [
                                asyncio.wait_for(
                                    twitter.process_reply(reply, commit, step_block, db), timeout=30
                                )
                                for reply in replies
                            ]
                            await asyncio.gather(*tasks, return_exceptions=True)
                        except Exception as commit_e:
                            error_msg = (
                                f"❌ Error processing commit {commit.hotkey}: {commit_e}"
                            )
                            logger.error(error_msg)
                            record_db_error(db, error_msg)
                            
                    current_block = await chain.wait_for_blocks(self.subtensor, db['last_set_weights'], constants.EPOCH_LENGTH, shutdown_event)
                    weights = chain.update_weights(self.metagraph, step_block, db)
                    logger.debug(f"Weights for block {step_block}: {weights}")
                    await self.subtensor.set_weights(
                        wallet=self.wallet,
                        netuid=self.config.netuid,
                        uids=list(range(len(weights))),
                        weights=weights,
                    )
                    db["last_set_weights"] = step_block
                    logger.info(f"✅ Updated weights on block {step_block}.")
                except Exception as e:
                    error_msg = (
                        f"❌ Error in main loop: {e}\nTraceback: {traceback.format_exc()}"
                    )
                    logger.error(error_msg)
                    record_db_error(db, error_msg)
                

            logger.info("👋 Shutdown event detected. Exiting main loop.")        
            
    async def run(self):
        shutdown_event = asyncio.Event()
        main_loop_task = asyncio.create_task(self.main_loop(shutdown_event=shutdown_event))

        db_path = Path(self.config.validator.db_filename)
        snapshot_db_path = str(db_path.with_name(db_path.stem + "_snapshot" + db_path.suffix))
        api_server_task = asyncio.create_task(
            run_api_server(
                db_filename=snapshot_db_path, 
                port=self.config.validator.db_api_port, 
                shutdown_event=shutdown_event
            )
        )
        await asyncio.gather(main_loop_task, api_server_task)
            
    async def __aenter__(self):
        logger.debug("Starting validator.")
        asyncio.create_task(self.run())
        logger.debug("Started validator.")
        return self
    
    async def __aexit__(self, exc_type, exc_value, traceback):
        pass
        
async def main():
    validator = Validator(get_config())
    await validator.setup_bittensor_objects()
    validator.setup_logging()
    
    async with validator:
        while True:
            logger.info("Validator is running...")
            await asyncio.sleep(constants.EPOCH_LENGTH // 4)
        
if __name__ == "__main__":
    asyncio.run(main())
