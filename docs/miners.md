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

4. Set up your X account with the required signature

    This step is crucial - validators will verify your X account using this signature.
    
    ```python
    # Generate your signature using Python
    import bittensor as bt

    # Initialize wallet
    wallet = bt.wallet(
        path='your_wallet_path',
        name='your_wallet_name', 
        hotkey='your_hotkey_name'
    )

    # X account username to sign
    x_account_username = 'your_x_username'

    # Generate signature
    signature = '0x' + wallet.hotkey.sign(x_account_username).hex()

    # Print results
    print(f'X Username: {x_account_username}')
    print(f'Signature: {signature}')
    ```
    
    Update your X account profile:
    - Add the generated signature to your X account's description/bio
    - Make sure your X account is public and has posting activity
    
5. Commit your X account to the chain

    Run the miner script to commit your X account to the chain:
    
    ```sh
    # Run the miner script
    python -m neurons.miner.miner \
        --netuid {netuid} \
        --wallet.path "your_wallet_path" \
        --wallet.name "your_wallet_name" \
        --wallet.hotkey "your_hotkey_name" \
        --subtensor.network finney
    
    # When prompted, enter your X account username
    ```

## Maintaining Your Miner Status

- Keep your X account active by posting content relevant to Bittensor
- Ensure your signature remains in your profile description
- Validators will automatically score your content based on the subnet's criteria

## Troubleshooting

If you encounter issues:

- Verify your wallet is registered: `btcli subnets show`
- Check your X account is properly set up with the signature
- Ensure your X account is public and active
- Try recommitting your X account username if validators aren't picking up your content
