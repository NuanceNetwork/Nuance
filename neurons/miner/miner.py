import asyncio

import bittensor as bt
from loguru import logger

from neurons.config import get_config

class Miner:
    def __init__(self, config: bt.Config):
        self.config = config

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
                f"\nYour miner: {self.wallet} is not registered to chain connection: {self.subtensor} \nRun 'btcli register' and try again."
            )
            exit()
        else:
            self.uid = self.metagraph.hotkeys.index(self.wallet.hotkey.ss58_address)
            logger.info(f"Running miner on uid: {self.uid}")
            
    async def run(self):
        "Miner input X account username, verification post id and commit to the chain"
        logger.info("📢 Make sure you have already created a verification post on X before proceeding. 📝")
        x_account_username = input("Enter your X account username: ")
        verification_post_id = input("Enter your verification post id: ")
        try:
            commit_data = f"{x_account_username}@{verification_post_id}"
            await self.subtensor.commit(wallet=self.wallet, netuid=self.config.netuid, data=commit_data)            
            logger.info(f"🎉 \033[92mYou have committed X account with username: {x_account_username} with verification post id: {verification_post_id} to the chain\033[0m 🚀")
        except Exception as e:
            logger.error(f"Error committing to chain: {e}")
            
async def main():
    miner = Miner(get_config())
    await miner.setup_bittensor_objects()
    await miner.run()

if __name__ == "__main__":
    asyncio.run(main())
