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
        "Miner input X account u and commit to the chain"
        x_account_username = input("Enter your X account username: ")
        try:
            await self.subtensor.commit(wallet=self.wallet, netuid=self.config.netuid, data=x_account_username)
            logger.info(f"X account username: {x_account_username} committed to chain")
        except Exception as e:
            logger.error(f"Error committing to chain: {e}")
            
async def main():
    miner = Miner(get_config())
    await miner.setup_bittensor_objects()
    await miner.run()

if __name__ == "__main__":
    asyncio.run(main())
