import asyncio

import aiohttp
import bittensor as bt

from nuance.models import PlatformType
from nuance.utils.logging import logger
from nuance.utils.bittensor_utils import (
    get_subtensor,
    get_wallet,
    get_metagraph,
    get_axons,
)
from nuance.utils.epistula import create_request
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

    async def submit(
        self,
        platform: PlatformType,
        verification_post_id: str,
        account_id: str = "",
        username: str = "",
        post_id: str = "",
        interaction_id: str = "",
    ):
        """Submit data to validators 's submission servers"""
        assert account_id or username, "Must provide either account_id or username"
        assert post_id or (not interaction_id), "Interaction ID requires a post ID"

        data = {
            "platform": platform,
            "account_id": account_id,
            "username": username,
            "verification_post_id": verification_post_id,
            "post_id": post_id,
            "interaction_id": interaction_id,
        }

        all_axons = await get_axons()
        all_validator_axons = []
        for axon in all_axons:
            axon_hotkey = axon.hotkey
            if axon_hotkey not in self.metagraph.hotkeys:
                continue
            axon_uid = self.metagraph.hotkeys.index(axon_hotkey)
            if self.metagraph.validator_permit[axon_uid] and axon.ip != "0.0.0.0":
                all_validator_axons.append(axon)

        # Inner method to send request to a single axon
        async def send_request_to_axon(axon: bt.AxonInfo):
            url = f"http://{axon.ip}:{axon.port}/submit"  # Update with the correct URL endpoint
            request_body_bytes, request_headers = create_request(
                data=data,
                sender_keypair=self.wallet.hotkey,
                receiver_hotkey=axon.hotkey
            )

            try:
                async with aiohttp.ClientSession() as session:
                    async with session.post(url, json=data, headers=request_headers) as response:
                        if response.status == 200:
                            return {'axon': axon.hotkey, 'status': response.status, 'response': await response.json()}
                        else:
                            error_message = await response.text()  # Capture response message for error details
                            return {'axon': axon.hotkey, 'status': response.status, 'error': error_message}
            except Exception as e:
                return {'axon': axon.hotkey, 'status': 'error', 'error': str(e)}

        # Send requests concurrently
        tasks = [send_request_to_axon(axon) for axon in all_validator_axons]
        responses = await asyncio.gather(*tasks, return_exceptions=True)

        for response in responses:
            if isinstance(response, Exception):
                logger.error(f"Exception occurred: {response}")
            else:
                if "error" in response:
                    logger.error(f"Error while sending to axon {response['axon']}: {response['error']}")
                else:
                    logger.info(f"Successfully submitted to axon {response['axon']} with status {response['status']}")


    async def run(self):
        "Miner input X account username, verification post id and commit to the chain"
        logger.info(
            "📢 Make sure you have already created a verification post on X before proceeding. 📝"
        )
        x_account_username = input("Enter your X account username: ")
        verification_post_id = input("Enter your verification post id: ")
        try:
            commit_data = f"{x_account_username}@{verification_post_id}"
            await self.subtensor.commit(
                wallet=self.wallet, netuid=settings.NETUID, data=commit_data
            )
            logger.info(
                f"🎉 \033[92mYou have committed X account with username: {x_account_username} with verification post id: {verification_post_id} to the chain\033[0m 🚀"
            )
        except Exception as e:
            logger.error(f"Error committing to chain: {e}")


async def main():
    miner = Miner()
    await miner.initialize()
    await miner.run()


if __name__ == "__main__":
    asyncio.run(main())
