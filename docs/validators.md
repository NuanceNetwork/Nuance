# Validator Setup

## Minimum System Requirements

Below is the minimum system requirements for running a validator node on the Nuance Subnet:

- Ubuntu 22.04 LTS
- 8-Core CPU
- 16-GB RAM
- 512-GB Storage

## Setup Instructions
To set up a validator node on the Nuance Subnet, follow these steps:

1. Prerequisites

    Make sure your machine have **Python** and **pip** installed
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
    cd nuance

    # Enviroment setup with uv
    pip install uv
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

4. Configure API Keys

   The validation process use services provided by . You can provide these in two ways:

   **Option 1: Export as environment variables**
   ```sh
   # Export API keys
   export DATURA_API_KEY="your_datura_api_key_here"
   # Validator of Nuance get free access to NineteenAI services for validation by default so no API key is needed. We thank Nineteen for their generosity.
   # You can optionally provide your API key.
   export NINETEEN_API_KEY="your_nineteen_api_key_here"
   ```

   **Option 2: Create a .env file**
   ```sh
   # Create .env file in your project root
   cat > .env << EOF
   DATURA_API_KEY=your_datura_api_key_here
   NINETEEN_API_KEY=your_nineteen_api_key_here
   EOF
   ```

5. Start the validator node

   Before starting the validator, ensure your wallet is registered on the subnet:
   ```sh
   # Register your wallet if not already registered
   btcli register --wallet.name your_wallet_name --wallet.hotkey your_wallet_hotkey --netuid xxx
   ```

   Then start the validator using PM2:
   ```sh
   # Replace the placeholder values with your actual configuration
   pm2 start python --name "validator_sn{netuid}" \
       -- -m neurons.validator.validator \
       --netuid {netuid} \
       --wallet.path "your_wallet_path" \
       --wallet.name "your_wallet_name" \
       --wallet.hotkey "your_wallet_hotkey" \
       --subtensor.network finney \
       --validator.db_filename "validator.db" \
       --validator.db_api_port 8080

   # Check validator status
   pm2 status

   # View validator logs
   pm2 logs validator_sn{netuid}
   ```

   **Configuration Options:**
   - `--netuid`: Your subnet ID (required)
   - `--wallet.name`: Your wallet name (required)
   - `--wallet.hotkey`: Your wallet hotkey (required)
   - `--subtensor.network`: Network to connect to (default: finney)
   - `--validator.db_filename`: Database filename (default: validator.db)
   - `--validator.db_api_port`: API server port (default: 8080)
