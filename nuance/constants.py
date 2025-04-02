import csv

from loguru import logger
from nuance.settings import settings

SCORING_HOUR = 16
EPOCH_LENGTH = 3600 if not settings.TESTNET else 600

# Load Verified Usernames from CSV
def load_verified_usernames(csv_path: str = "verified.csv") -> set:
    """
    Load verified usernames from a CSV file.
    Assumes the CSV format: id, display name, username.
    Uses the last item (username) in each row for verification.
    """
    verified = set()
    try:
        with open(csv_path, newline="", encoding="utf-8") as csvfile:
            reader = csv.reader(csvfile)
            for row in reader:
                if row and len(row) >= 3:
                    username = row[-1].strip().lower()
                    verified.add(username)
        logger.info(f"✅ Loaded {len(verified)} verified usernames from {csv_path}.")
    except Exception as e:
        logger.error(f"❌ Failed to load verified users: {e}")
        raise
    return verified

VERIFIED_USERNAMES = load_verified_usernames()

NUANCE_CONSTITUTION_STORE_URL = "https://raw.githubusercontent.com/NuanceNetwork/constitution/refs/heads/main/" # Github URL
NUANCE_CONSTITUTION_UPDATE_INTERVAL = 3600 # 1 hour