---
hide:
  - navigation
#   - toc
---

# Miner Setup

## NEW SETUP INSTRUCTION
Please check our [**example notebook**](/examples/miner_signup.ipynb) for full interactive guide on how to setup your miner on Nuance. 

Additional helpful scripts and examples are available in the [`examples/`](/examples/) folder.

## Quick Links
- **📚 [Submit Content](https://www.docs.nuance.info/)** - Easy submission portal with API interface
- **🔗 [Check Your Scores](http://api.nuance.info/scalar)** - Monitor your performance and recent submissions
- **🐦 [Follow Updates](https://x.com/NuanceSubnet)** - Official announcements and subnet news

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

4. Verify your X account

    Choose one of these verification methods:
    
    **Method 1: Verification Post (Recommended)**
    - Create a post that **replies to** or **quotes** any post from [@NuanceSubnet](https://x.com/NuanceSubnet)
    - Include your hotkey address in the post text
    - Ensure your X account is public and active
    
    Example post text:
    ```
    I'm joining the Nuance Network as a miner with hotkey: 5F7nTtN...XhVVi
    ```
    
    **Method 2: Hashtag Verification**
    - Include the hashtag `#NuanceUID` in your posts, where `UID` is your miner's UID in the subnet
    - Example: If your UID is 42, use `#Nuance42` in your posts
    - Find your UID by checking `btcli subnets show` after registration
    
    Save your verification post ID if using Method 1.

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
    
    # When prompted, enter your X account username and verification post ID (if using Method 1)
    ```

## Content Submission & Scoring

### How to Submit Content

**Option 1: Documentation Portal (Recommended)**
- Visit [docs.nuance.info](https://www.docs.nuance.info/) for easy content submission
- User-friendly interface for non-technical users
- Immediate submission confirmation

**Option 2: Direct API Submission**
- Submit directly to validator axons (check metagraph for validator endpoints)
- For technical users comfortable with API calls
- See [`examples/simple_submission.ipynb`](../examples/simple_submission.ipynb) for implementation details

**Option 3: Automatic Discovery (Being Phased Out)**
- Validators currently still scrape content from verified miners' X accounts
- This method will be removed in future updates

### Scoring System

Your rewards are calculated based on:

- **Engagement Quality**: Positive interactions (replies) from verified community members
- **Account Status**: If you own a verified account, your own posts contribute to your score
- **7-Day Window**: Only content and interactions from the last 7 days count
- **Anti-Spam Protection**: Scoring is capped per user to prevent gaming
- **Topic Relevance**: Content scored based on current focus areas

## Maintaining Your Miner Status

- Keep your X account active by posting factual, nuanced content
- Submit your best content through the [documentation portal](https://www.docs.nuance.info/)
- Monitor your performance via the [API explorer](http://api.nuance.info/scalar)
- Follow [@NuanceSubnet](https://x.com/NuanceSubnet) for updates and announcements
- Check out [miner tips](../examples/miner_tips.ipynb) for Nuance Subnet best practices

## Troubleshooting

If you encounter issues:

- **Registration**: Verify your wallet is registered with `btcli subnets show`
- **Verification**: Check that your verification post/hashtags:
  - Are public and accessible
  - Contain your exact hotkey address
  - Follow the correct format for your chosen method
- **Submissions**: Try the [documentation portal](https://www.docs.nuance.info/) if direct submission isn't working
- **Scoring**: Use the [API explorer](http://api.nuance.info/scalar) to check your recent submissions and scores
- **Account Issues**: Ensure your X account is public and active

For additional help, refer to the [full documentation](https://www.docs.nuance.info/) or follow [@NuanceSubnet](https://x.com/NuanceSubnet) for support updates.