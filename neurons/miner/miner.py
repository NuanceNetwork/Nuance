import asyncio

import bittensor as bt

from neurons.config import get_config

class Miner:
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
                f"\nYour miner: {self.wallet} is not registered to chain connection: {self.subtensor} \nRun 'btcli register' and try again."
            )
            exit()
        else:
            self.uid = self.metagraph.hotkeys.index(self.wallet.hotkey.ss58_address)
            bt.logging.info(f"Running miner on uid: {self.uid}")
            
    def run(self):
        "Miner input X account id and commit to the chain"
        account_id = input("Enter your X account id: ")
        try:
            asyncio.run(self.subtensor.commit(wallet=self.wallet, netuid=self.config.netuid, data=account_id))
            bt.logging.info(f"X account id: {account_id} committed to chain")
        except Exception as e:
            bt.logging.error(f"Error committing to chain: {e}")
                
if __name__ == "__main__":
    miner = Miner(get_config())
    miner.run()
