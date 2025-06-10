# neurons/validator/submission_server/models.py
import time
from pydantic import BaseModel, Field
from nuance.models import PlatformType


class SubmissionData(BaseModel):
    """Content submission payload from miners - one item per request"""
    platform: PlatformType
    account_id: str
    verification_post_id: str
    post_id: str
    interaction_id: str

class GossipData(BaseModel):
    """Gossip payload between validators"""
    original_body_model: str  # Fully qualified name, e.g., "neurons.validator.submission_server.models.SubmissionData"
    original_body_hex: str
    original_headers: dict[str, str]
    forwarded_at: int = Field(default_factory=lambda: int(time.time() * 1000))


MODEL_REGISTRY = {
    "SubmissionData": SubmissionData,
}