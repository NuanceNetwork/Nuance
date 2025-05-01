# Validator Setup

## Minimum System Requirements

Below is the minimum system requirements for running a validator node on the Nuance Subnet:

- Ubuntu 22.04 LTS
- 8-Core CPU
- 16-GB RAM
- 512-GB Storage
- Docker and Docker Compose

## Setup Instructions
To set up a validator node on the Nuance Subnet, follow these steps:

1. Prerequisites

    Make sure your machine have **Python**, **pip**, **Docker** and **Docker Compose** installed
    ```sh
    # Install Python 3.10
    sudo apt update
    sudo apt install python3.10 python3.10-venv python3.10-dev

    # Install pip for Python 3.10
    curl -sS https://bootstrap.pypa.io/get-pip.py | python3.10

    # Install Docker
    sudo apt install apt-transport-https ca-certificates curl software-properties-common
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo apt-key add -
    sudo add-apt-repository "deb [arch=amd64] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable"
    sudo apt update
    sudo apt install docker-ce
    # Check Docker installation
    docker --version
    docker run hello-world

    # Install Docker Compose
    sudo curl -L "https://github.com/docker/compose/releases/download/v2.24.6/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
    sudo chmod +x /usr/local/bin/docker-compose

    # Add your user to the docker group to run docker without sudo
    sudo usermod -aG docker $USER
    # Log out and log back in for this to take effect

    # Verify installations
    python3.10 --version
    pip --version
    docker --version
    docker-compose --version
    ```

2. Install the latest version of the Nuance Subnet repository
    ```sh
    # Clone the repository
    git clone https://github.com/NuanceNetwork/Nuance
    cd nuance

    # Environment setup with uv
    sudo pip install uv
    uv sync
    ```

3. Install PM2 Process Manager

    - NVM (Node Version Manager): <https://github.com/nvm-sh/nvm>
    - Node.js and npm: <https://nodejs.org/en/download>
    - PM2 (Process Manager): <https://pm2.io/docs/runtime/guide/installation>

    ```sh
    # Install NVM (Node Version Manager):
    curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.2/install.sh | bash

    # Activate NVM:
    source ~/.bashrc

    # Check NVM version:
    nvm --version

    # Install Node.js and npm:
    nvm install --latest-npm --alias=default [NODE_VERSION]
    # For example:
    nvm install --latest-npm --alias=default 22.14.0

    # Set the default Node.js:
    nvm use default

    # Check Node.js and npm versions:
    node --version
    npm --version

    # Install PM2 globally with logrotate:
    npm install -g pm2
    pm2 install pm2-logrotate

    # Check PM2 version:
    pm2 --version
    ```

4. Configure Environment Variables

    Create a `.env` file in the project root. You can use the provided `.env.example` as a template:

    ```sh
    # Copy the example file
    cp .env.example .env
    
    # Edit the file with your values
    nano .env
    ```

    At minimum, you need to set:
    ```
    # Bittensor settings
    WALLET_PATH=~/.bittensor/wallets
    WALLET_NAME=your_wallet_name
    WALLET_HOTKEY=your_hotkey_name
    
    # API Keys
    DATURA_API_KEY=your_datura_api_key_here
    
    # Database configuration
    DATABASE_URL=postgresql+asyncpg://user:password@127.0.0.1:5432/nuance
    ```

    The `.env` file supports many configuration options:
    ```
    # Environment settings
    NETUID=23                  # Subnet ID
    DEBUG=False                # Set to False in production
    SUBTENSOR_NETWORK=finney   # Subtensor network to use

    # Bittensor settings
    WALLET_PATH=~/.bittensor/wallets
    WALLET_NAME=your_wallet_name
    WALLET_HOTKEY=your_hotkey_name

    # API Keys
    DATURA_API_KEY=your_datura_api_key_here
    NINETEEN_API_KEY=your_19_api_key        # Optional

    # Database configuration - should match docker-compose.yml
    DATABASE_URL=postgresql+asyncpg://user:password@127.0.0.1:5432/nuance
    
    # Database connection pool settings
    DATABASE_POOL_SIZE=5
    DATABASE_MAX_OVERFLOW=10
    DATABASE_POOL_TIMEOUT=30
    DATABASE_ECHO=False
    ```

5. Start the validator node

   Before starting the validator, ensure your wallet is registered on the subnet:
   ```sh
   # Register your wallet if not already registered
   btcli register --wallet.name your_wallet_name --wallet.hotkey your_wallet_hotkey --netuid 23
   ```

   You can start the validator manually with the following steps:

   ```sh
   # Sync uv dependencies
   uv sync

   # Start the PostgreSQL database using Docker Compose
   docker-compose up -d

   # Run alembic migrations
   uv run alembic upgrade head

   # Start the validator with PM2
   pm2 start uv --name "validator_sn23" -- run python -m neurons.validator.main
   
   # Check validator status
   pm2 status
   
   # View validator logs
   pm2 logs validator_sn23
   ```

   ### Automated Startup (Alternative)

   Alternatively, you can use the provided startup script to automate these steps:

   ```sh
   # Make the script executable
   chmod +x ./scripts/run_validator.sh

   # Run the script
   ./scripts/run_validator.sh
   ```

   The script will:
   1. Sync uv dependencies
   2. Start the PostgreSQL database
   3. Run the Alembic migrations
   4. Start the validator with PM2

   The validator will read all configuration from your `.env` file, so you don't need to pass any parameters as command-line arguments.