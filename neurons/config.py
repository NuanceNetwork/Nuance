import os
from argparse import ArgumentParser

import bittensor as bt
from loguru import logger

def get_config(parser=ArgumentParser()) -> bt.Config:
    bt.wallet.add_args(parser)
    bt.subtensor.add_args(parser)
    bt.axon.add_args(parser)
    bt.logging.add_args(parser)
    config = bt.config(parser)
    bt.logging.check_config(config)
    full_path = os.path.expanduser(
        "{}/{}/{}/netuid-{}".format(
            config.logging.logging_dir,
            config.wallet.name,
            config.wallet.hotkey,
            config.netuid,
        )
    )
    config.neuron.fullpath = os.path.expanduser(full_path)
    if not os.path.exists(config.neuron.fullpath):
        os.makedirs(config.neuron.fullpath, exist_ok=True)
    return config