import datetime
from typing import Optional
from pydantic import BaseModel, Field

from nuance.models import ProcessingStatus


class MinerScore(BaseModel):
    """Model for a miner's score."""
    node_hotkey: str = Field(..., description="Miner's hotkey")
    score: float = Field(..., description="Miner's score")

class MinerScoresResponse(BaseModel):
    """Response model for miner scores."""
    miner_scores: list[MinerScore] = Field(..., description="List of miner scores")

class MinerStatsResponse(BaseModel):
    """Response model for miner statistics."""
    
    node_hotkey: str = Field(..., description="Miner's hotkey")
    account_count: int = Field(..., description="Number of verified social accounts")
    post_count: int = Field(..., description="Number of posts submitted")
    interaction_count: int = Field(..., description="Number of interactions received")


class AccountVerificationResponse(BaseModel):
    """Response model for account verification."""
    
    platform_type: str = Field(..., description="Social media platform type")
    account_id: str = Field(..., description="Platform-specific account ID")
    username: str = Field(..., description="Account username")
    node_hotkey: Optional[str] = Field(None, description="Associated miner hotkey")
    node_netuid: Optional[int] = Field(None, description="Associated network UID")
    is_verified: bool = Field(..., description="Whether the account is verified")


class PostVerificationResponse(BaseModel):
    """Response model for post verification status."""
    
    platform_type: str = Field(..., description="Social media platform type")
    post_id: str = Field(..., description="Platform-specific post ID")
    content: str = Field(..., description="Post content")
    topics: list[str] = Field(default=[], description="Topics identified in the post")
    processing_status: str = Field(..., description="Current processing status")
    processing_note: Optional[str] = Field(None, description="Additional processing information")
    interaction_count: int = Field(default=0, description="Number of interactions with this post")
    created_at: datetime.datetime = Field(..., description="Date and time the post was created")


class InteractionResponse(BaseModel):
    """Response model for interaction details."""
    
    platform_type: str = Field(..., description="Social media platform type")
    interaction_id: str = Field(..., description="Platform-specific interaction ID")
    interaction_type: str = Field(..., description="Type of interaction (reply, like, etc.)")
    post_id: str = Field(..., description="ID of the parent post")
    account_id: str = Field(..., description="ID of the account that made this interaction")
    content: Optional[str] = Field(None, description="Content of the interaction (if applicable)")
    processing_status: ProcessingStatus = Field(..., description="Current processing status")
    processing_note: Optional[str] = Field(None, description="Additional processing information")
    created_at: datetime.datetime = Field(..., description="Date and time the interaction was created")