# neurons/validator/submission_server/models.py
import time
from pydantic import BaseModel, Field, field_validator
from nuance.models import PlatformType


class SubmissionData(BaseModel):
    """Content submission payload from miners - one item per request"""
    platform: PlatformType
    account_id: str = ""
    username: str = ""
    verification_post_id: str
    post_id: str = ""
    interaction_id: str = ""
    
    @field_validator("username")
    def validate_account_identifier(cls, v, values):
        if not v and not values.get("account_id"):
            raise ValueError("Must provide either account_id or username")
        return v
    
    @field_validator("interaction_id")
    def validate_interaction_requires_post(cls, v, values):
        if v and not values.get("post_id"):
            raise ValueError("Interaction ID requires a post ID")
        return v

class GossipData(BaseModel):
    """Gossip payload between validators"""
    original_body_model: str  # Fully qualified name, e.g., "neurons.validator.submission_server.models.SubmissionData"
    original_body_hex: str
    original_headers: dict[str, str]
    forwarded_at: int = Field(default_factory=lambda: int(time.time() * 1000))


MODEL_REGISTRY = {
    "SubmissionData": SubmissionData,
}