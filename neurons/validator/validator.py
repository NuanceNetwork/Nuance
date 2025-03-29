import time
import asyncio
from collections import defaultdict
import shelve
import threading
import traceback

import bittensor as bt

from neurons.config import get_config
from neurons.validator.api_server import run_api_server
import nuance.constants as constants
import nuance.chain as chain
import nuance.twitter as twitter
from nuance.utils import record_db_error

class Validator:
    def __init__(self, config: bt.Config):
        self.config = config
        asyncio.run(self.setup_bittensor_objects())
        
    async def setup_bittensor_objects(self):
        bt.logging.info("Setting up Bittensor objects.")
        self.wallet = bt.wallet(config=self.config)
        bt.logging.info(f"Wallet: {self.wallet}")
        self.subtensor = bt.async_subtensor(config=self.config)
        await self.subtensor.initialize()
        self.metagraph = await self.subtensor.metagraph(self.config.netuid)
        bt.logging.info(f"Metagraph: {self.metagraph}")

        if self.wallet.hotkey.ss58_address not in self.metagraph.hotkeys:
            bt.logging.error(
                f"\nYour validator: {self.wallet} is not registered to chain connection: {self.subtensor} \nRun 'btcli register' and try again."
            )
            exit()
        else:
            self.uid = self.metagraph.hotkeys.index(self.wallet.hotkey.ss58_address)
            bt.logging.info(f"Running validator on uid: {self.uid}")
            
            
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
            db.setdefault("parent_tweets", [])
            db.setdefault("child_replies", [])
            db.setdefault("errors", [])

            while not shutdown_event.is_set():
                try:
                    step_block = await self.subtensor.get_current_block()
                    db["step_blocks"].append(step_block)
                    bt.logging.info(f"🔄 Processing block {step_block}.")

                    commits = await chain.get_commitments(
                        subtensor=self.subtensor, metagraph=self.metagraph, netuid=self.config.netuid
                    )
                    bt.logging.info(f"✅ Pulled {len(commits)} commits.")

                    for commit in commits.values():
                        try:
                            replies = await twitter.get_all_replies(commit.account_id)
                            bt.logging.info(
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
                            bt.logging.error(error_msg)
                            record_db_error(db, error_msg)

                    weights = chain.update_weights(self.metagraph, step_block, db)
                    await self.subtensor.set_weights(
                        wallet=self.wallet,
                        netuid=self.config.netuid,
                        uids=list(range(len(weights))),
                        weights=weights,
                    )
                    db["last_set_weights"] = step_block
                    bt.logging.info(f"✅ Updated weights on block {step_block}.")
                except Exception as e:
                    error_msg = (
                        f"❌ Error in main loop: {e}\nTraceback: {traceback.format_exc()}"
                    )
                    bt.logging.error(error_msg)
                    record_db_error(db, error_msg)

            bt.logging.info("👋 Shutdown event detected. Exiting main loop.")        
            
    def run(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        shutdown_event = asyncio.Event()
        loop.create_task(self.main_loop(shutdown_event=shutdown_event))
        loop.create_task(
            run_api_server(
                db_filename=self.config.validator.db_filename, 
                port=self.config.validator.db_api_port, 
                shutdown_event=shutdown_event
            )
        )
        loop.run_forever()
            
    def __enter__(self):
        bt.logging.debug("Starting validator in background thread.")
        self.thread = threading.Thread(target=self.run, daemon=True)
        self.thread.start()
        bt.logging.debug("Started")
        return self
    
    def __exit__(self, exc_type, exc_value, traceback):
        pass
    
    def handle_signal(self, signum, frame):
        bt.logging.info(f"Received signal {signum}. Exiting...")
        exit()
        
if __name__ == "__main__":
    with Validator(get_config()) as validator:
        while True:
            bt.logging.info("Validator is running...")
            time.sleep(constants.EPOCH_LENGTH // 4)
