---
hide:
  - navigation
#   - toc
---

# Miner Setup

## Setup Instructions
To set up a miner node on the Nuance Subnet, follow these steps:

1. Prerequisites

    Make sure your machine has **Python** and **pip** installed
    ```sh
    # Install Python 3.10
    sudo apt update
    sudo apt install python3.10 python3.10-venv python3.10-dev

    # Install pip for Python 3.10
    curl -sS https://bootstrap.pypa.io/get-pip.py | python3.10

    # Verify installations
    python3.10 --version
    pip --version
    ```

2. Install the latest version of the Nuance Subnet repository
    ```sh
    # Clone the repository
    git clone https://github.com/NuanceNetwork/Nuance
    cd nuance-subnet

    # Environment setup with uv
    pip install uv
    uv sync
    ```

3. Register your wallet on the Nuance Subnet

    ```sh
    # Create a wallet if you don't have one
    btcli wallet new --wallet.name your_wallet_name --wallet.hotkey your_hotkey_name
    
    # Register on the subnet
    btcli register --wallet.name your_wallet_name --wallet.hotkey your_hotkey_name --netuid {netuid}
    
    # Check your registration status
    btcli subnets show
    ```

4. Create a verification post on your X account

    This step is crucial - validators will verify your X account using this post.
    
    - Ensure your X account is public and has posting activity
    - Create a new post that **quotes** the [Nuance announcement post](https://x.com/NuanceSubnet/status/1909263356654952674)
    - Include your hotkey address in the post text
    
    Example post text:
    ```
    I'm joining the Nuance Network as a miner with hotkey: 5F7nTtN...XhVVi
    ```
    
    Save the verification post ID as you'll need it for the next step.

5. Set environment variables

    Create an `.env` file in the root directory of the project to configure environment variables. This file will be automatically loaded at runtime.
    
    Example `.env` file:
    ```
    NETUID=23
    SUBTENSOR_NETWORK=finney
    WALLET_PATH=~/.bittensor/wallets
    WALLET_NAME=my_wallet
    WALLET_HOTKEY=my_hotkey
    ```

    Alternatively, you can run the following command to set up the `.env` file with the same values:
    ```sh
    echo -e "NETUID=23\nSUBTENSOR_NETWORK=finney\nWALLET_PATH=~/.bittensor/wallets\nWALLET_NAME=my_wallet\nWALLET_HOTKEY=my_hotkey" > .env
    ```
    
6. Commit your X account to the chain

    Run the miner script to commit your X account to the chain:
    
    ```sh
    # Run the miner script
    uv run python -m neurons.miner.main
    
    # When prompted, enter your X account username and verification post ID
    ```

## Maintaining Your Miner Status

- Keep your X account active by posting content relevant to Bittensor
- Make sure your verification post remains accessible
- Validators will automatically score your content based on the subnet's criteria
- Checkout [miner tips](../examples/miner_tips.ipynb) for Nuance Subnet

## Troubleshooting

If you encounter issues:

- Verify your wallet is registered: `btcli subnets show`
- Check that your verification post:
  - Is public and accessible
  - Contains your exact hotkey address
  - Is a quote tweet of the Nuance announcement post
- Ensure your X account is public and active
- Try recommitting your X account username and verification post ID if validators aren't picking up your content
