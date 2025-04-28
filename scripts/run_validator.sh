#!/bin/bash
set -e

echo "=== Starting Nuance Validator ==="

# 1. Start PostgreSQL database
echo "Starting PostgreSQL database..."
docker-compose up -d
echo "PostgreSQL database started."

# Wait to ensure database is ready
sleep 5

# 2. Run Alembic migrations
echo "Running database migrations..."
uv run alembic upgrade head
echo "Database migrations completed."

# 3. Start the validator with PM2
echo "Starting validator with PM2..."
pm2 start uv --name "validator_sn23" -- run python -m neurons.validator.main
echo "Validator started successfully."

# Show status
echo
echo "Nuance Validator is now running."
echo "View validator status: pm2 status"
echo "View validator logs: pm2 logs validator_sn23"
echo "Stop validator: pm2 stop validator_sn23"