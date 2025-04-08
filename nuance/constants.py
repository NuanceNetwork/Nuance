import csv

from loguru import logger
from nuance.settings import settings

SCORING_HOUR = 16
EPOCH_LENGTH = 300 if not settings.TESTNET else 50 # blocks (12s per block)

NUANCE_CONSTITUTION_STORE_URL = "https://raw.githubusercontent.com/NuanceNetwork/constitution/refs/heads/main/" # Github URL
NUANCE_CONSTITUTION_UPDATE_INTERVAL = 3600 # 1 hour

NUANCE_ANNOUNCEMENT_POST_ID = "1909263356654952674"