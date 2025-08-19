import datetime
from typing import Optional
from pydantic import BaseModel, Field

from nuance.models import ProcessingStatus, PlatformType


class MinerScore(BaseModel):
    """Model for a miner's score."""
    node_hotkey: str = Field(..., description="Miner's hotkey")
    score: float = Field(..., description="Miner's score")


class MinerScoresResponse(BaseModel):
    """Response model for miner scores."""
    miner_scores: list[MinerScore] = Field(..., description="List of miner scores")


class CategoryScoreItem(BaseModel):
    type: str = Field(..., description="Type of content (post or interaction)")
    id: str = Field(..., description="Content ID")
    platform: str = Field(..., description="Platform type (twitter, etc.)")
    raw_score: float = Field(..., description="Raw score for this category")
    normalized_contribution: float = Field(..., description="Contribution to this category's normalized score")

class CategoryBreakdown(BaseModel):
    normalized_score: float = Field(..., description="Miner's normalized score in this category")
    items: list[CategoryScoreItem] = Field(..., description="Items contributing to this category")


class MinerScoreBreakdownResponse(BaseModel):
    node_hotkey: str = Field(..., description="Miner's hotkey")
    final_score: float = Field(..., description="Final weighted score across all categories")
    total_items: int = Field(..., description="Total number of scored items")
    categories: dict[str, CategoryBreakdown] = Field(..., description="Breakdown by category")


class MinerStatsResponse(BaseModel):
    """Response model for miner statistics."""
    node_hotkey: str = Field(..., description="Miner's hotkey")
    account_count: int = Field(..., description="Number of verified social accounts")
    post_count: int = Field(..., description="Number of posts submitted")
    interaction_count: int = Field(..., description="Number of interactions received")


class EngagementStats(BaseModel):

    def __add__(self, other: "EngagementStats") -> "EngagementStats":
        """Add two EngagementStats objects together using model_fields"""
        if not isinstance(other, self.__class__):
            return NotImplemented
            
        kwargs = {}
        for field_name in self.model_fields:
            self_val = getattr(self, field_name) or 0
            other_val = getattr(other, field_name) or 0
            result = self_val + other_val
            kwargs[field_name] = result if result > 0 else None
            
        return self.__class__(**kwargs)
    
    def __radd__(self, other):
        """Support sum() function"""
        if other == 0:
            return self
        return self.__add__(other)
    
    @classmethod
    def zero(cls) -> "EngagementStats":
        """Create a zero-valued EngagementStats object"""
        return cls(**{field: 0 for field in cls.model_fields})

class TwitterEngagementStats(EngagementStats):
    view_count: Optional[int] = None
    reply_count: Optional[int] = None
    retweet_count: Optional[int] = None
    like_count: Optional[int] = None
    quote_count: Optional[int] = None
    bookmark_count: Optional[int] = None

# Union of stats type for different platform types
EngagementStatsType = TwitterEngagementStats
    

class AccountVerificationResponse(BaseModel):
    """Response model for account verification."""
    platform_type: PlatformType = Field(..., description="Social media platform type")
    account_id: str = Field(..., description="Platform-specific account ID")
    username: str = Field(..., description="Account username")
    node_hotkey: Optional[str] = Field(None, description="Associated miner hotkey")
    node_netuid: Optional[int] = Field(None, description="Associated network UID")
    is_verified: bool = Field(..., description="Whether the account is verified")


class PostVerificationResponse(BaseModel):
    """Response model for post verification status."""
    platform_type: PlatformType = Field(..., description="Social media platform type")
    post_id: str = Field(..., description="Platform-specific post ID")
    account_id: str = Field(..., description="Account that made the post")
    content: str = Field(..., description="Post content")
    topics: list[str] = Field(default=[], description="Topics identified in the post")
    processing_status: str = Field(..., description="Current processing status")
    processing_note: Optional[str] = Field(None, description="Additional processing information")
    interaction_count: int = Field(default=0, description="Number of interactions with this post")
    created_at: datetime.datetime = Field(..., description="Date and time the post was created")
    username: Optional[str] = Field(default="", description="Username of the account that made the post")
    profile_pic_url: Optional[str] = Field(default="", description="URL of the account's profile picture")
    stats: Optional[EngagementStatsType] = None


class InteractionResponse(BaseModel):
    """Response model for interaction details."""
    platform_type: PlatformType = Field(..., description="Social media platform type")
    interaction_id: str = Field(..., description="Platform-specific interaction ID")
    interaction_type: str = Field(..., description="Type of interaction (reply, like, etc.)")
    post_id: str = Field(..., description="ID of the parent post")
    account_id: str = Field(..., description="ID of the account that made this interaction")
    content: Optional[str] = Field(None, description="Content of the interaction (if applicable)")
    processing_status: ProcessingStatus = Field(..., description="Current processing status")
    processing_note: Optional[str] = Field(None, description="Additional processing information")
    created_at: datetime.datetime = Field(..., description="Date and time the interaction was created")
    stats: Optional[EngagementStatsType] = None


class TopPostItem(BaseModel):
    date: str = Field(description="Post date (YYYY-MM-DD format), created_at field from Post")
    handle: str = Field(description="Account username/handle made the post")
    text: str = Field(description="Post content")
    stats: Optional[EngagementStatsType] = None


class TopPostsResponse(BaseModel):
    posts: list[TopPostItem] = Field(..., description="List of top posts")
    period: str = Field(..., description="Time period for the ranking")
    total_count: int = Field(..., description="Total number of posts returned")


class TopMinerItem(BaseModel):
    """Item in top miners list - matches dashboard table structure"""
    uid: int = Field(..., description="Miner UID (e.g., 123)")
    handle: str = Field(..., description="Primary account handle/username")
    score: float = Field(..., description="Subnet score")
    retweet_count: int = Field(..., description="Number of retweets in the period")
    reply_count: int = Field(..., description="Number of replies in the period")
    node_hotkey: str = Field(..., description="Miner's hotkey")


class TopMinersResponse(BaseModel):
    """Response for top miners endpoint"""
    miners: list[TopMinerItem] = Field(..., description="List of miners")
    period: str = Field(..., description="Time period for the data")
    total_count: int = Field(..., description="Total number of miners returned")


class SubnetStatsSummary(BaseModel):
    account_count: int = Field(..., description="Number of verified social accounts")
    post_count: int = Field(..., description="Number of posts submitted")
    interaction_count: int = Field(..., description="Number of interactions received")
    engagement_stats: Optional[EngagementStatsType] = Field(..., description="Aggregated engagement statistics")