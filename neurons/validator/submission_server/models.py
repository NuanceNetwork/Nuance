# neurons/validator/submission_server/models.py
import time
from pydantic import BaseModel, Field, model_validator
from nuance.models import PlatformType


class SubmissionData(BaseModel):
    """Content submission payload from miners - one item per request"""
    platform: PlatformType
    account_id: str = ""
    username: str = ""
    verification_post_id: str
    post_id: str = ""
    interaction_id: str = ""
    
    @model_validator(mode='after')
    def validate_submission_data(self):
        """Validate cross-field relationships"""
        
        # Must provide either account_id or username
        if not self.username and not self.account_id:
            raise ValueError("Must provide either account_id or username")
        
        # Interaction ID requires a post ID
        if self.interaction_id and not self.post_id:
            raise ValueError("Interaction ID requires a post ID")
        
        return self

class GossipData(BaseModel):
    """Gossip payload between validators"""
    original_body_model: str  # One of the model in neurons/validator/submission_server/models.py
    original_body_hex: str
    original_headers: dict[str, str]
    forwarded_at: int = Field(default_factory=lambda: int(time.time() * 1000))


MODEL_REGISTRY = {
    "SubmissionData": SubmissionData,
}