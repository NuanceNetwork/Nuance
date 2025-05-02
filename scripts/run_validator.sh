#!/bin/bash
set -e

echo "=== Starting Nuance Validator ==="

# Check if .env file exists
if [ ! -f .env ]; then
    echo "Error: .env file not found. Please create one based on .env.example"
    exit 1
fi

# 1. Sync dependencies
echo "Syncing dependencies with uv..."
uv sync
echo "Dependencies synced successfully."

# 2. Start PostgreSQL database
echo "Starting PostgreSQL database..."
if ! docker compose up -d; then
    echo "Error: Failed to start PostgreSQL database"
    exit 1
fi
echo "PostgreSQL database started."

# Wait to ensure database is ready
echo "Waiting for database to be ready..."
sleep 5

# 3. Run Alembic migrations
echo "Running database migrations..."
if ! uv run alembic upgrade head; then
    echo "Error: Failed to run database migrations"
    exit 1
fi
echo "Database migrations completed."

# 4. Check if validator is already running
if pm2 list | grep -q "validator_sn23"; then
    echo "Validator is already running. Restarting..."
    pm2 restart validator_sn23
else
    # 5. Start the validator with PM2
    echo "Starting validator with PM2..."
    if ! pm2 start uv --name "validator_sn23" -- run python -m neurons.validator.main; then
        echo "Error: Failed to start validator"
        exit 1
    fi
    echo "Validator started successfully."
fi

# Show status
echo
echo "=== Nuance Validator Status ==="
echo "Validator is now running."
echo
echo "Commands:"
echo "  View validator status: pm2 status"
echo "  View validator logs: pm2 logs validator_sn23"
echo "  Stop validator: pm2 stop validator_sn23"
echo "  Restart validator: pm2 restart validator_sn23"
echo
echo "Note: Make sure your wallet is registered on the subnet using:"
echo "  btcli register --wallet.name your_wallet_name --wallet.hotkey your_wallet_hotkey --netuid 23"