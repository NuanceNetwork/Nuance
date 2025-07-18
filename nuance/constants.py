# nuance/constants.py
from nuance.settings import settings


EPOCH_LENGTH = 300 * 12 if not settings.DEBUG else 50 * 12 # seconds

NUANCE_CONSTITUTION_STORE_URL = "https://github.com/NuanceNetwork/constitution" # Github URL
NUANCE_CONSTITUTION_BRANCH = "main"  # Branch name for constitution repo
NUANCE_CONSTITUTION_UPDATE_INTERVAL = 3600 # 1 hour

NUANCE_ANNOUNCEMENT_POST_ID = "1909263356654952674"
NUANCE_SOCIAL_ACCOUNT_ID = "1748721804925952000"

ALPHA_BURN_RATIO = 0.7

SCORING_WINDOW = 7 # days

LOG_URL = "https://log.nuance.network/api/logs"