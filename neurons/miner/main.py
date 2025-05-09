import asyncio

import bittensor as bt

from nuance.utils.logging import logger
from nuance.utils.bittensor_utils import get_subtensor, get_wallet, get_metagraph
from nuance.settings import settings

class Miner:
    def __init__(self):
        # Bittensor objects
        self.subtensor: bt.AsyncSubtensor = None  # Will be initialized later
        self.wallet: bt.Wallet = None  # Will be initialized later
        self.metagraph: bt.Metagraph = None  # Will be initialized later
        

    async def initialize(self):
        # Initialize bittensor objects
        self.subtensor = await get_subtensor()
        self.wallet = await get_wallet()
        self.metagraph = await get_metagraph()
        
        # Check if miner is registered to chain
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
            await self.subtensor.commit(wallet=self.wallet, netuid=settings.NETUID, data=commit_data)            
            logger.info(f"🎉 \033[92mYou have committed X account with username: {x_account_username} with verification post id: {verification_post_id} to the chain\033[0m 🚀")
        except Exception as e:
            logger.error(f"Error committing to chain: {e}")
            
async def main():
    miner = Miner()
    await miner.initialize()
    await miner.run()

if __name__ == "__main__":
    asyncio.run(main())
