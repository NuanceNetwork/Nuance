from nuance.settings import settings


SCORING_HOUR = 16
EPOCH_LENGTH = 300 * 12 if not settings.DEBUG else 50 * 12 # seconds

NUANCE_CONSTITUTION_STORE_URL = "https://github.com/NuanceNetwork/constitution" # Github URL
NUANCE_CONSTITUTION_BRANCH = "dev-haihp02"  # Branch name for constitution repo
NUANCE_CONSTITUTION_UPDATE_INTERVAL = 3600 # 1 hour

NUANCE_ANNOUNCEMENT_POST_ID = "1909263356654952674"

TOPICS = [
    "bittensor",
    "nuance_subnet"
]

CATEGORIES_WEIGHTS = {
    "bittensor": 0.4,
    "nuance_subnet": 0.4,
    "other": 0.2
}

SCORING_WINDOW = 14 # days

LOG_URL = "https://log.nuance.network/api/logs"