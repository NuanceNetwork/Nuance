# nuance/models/domain.py
from pydantic import BaseModel, Field
from typing import Any, Optional
from enum import Enum


class PlatformType(str, Enum):
    TWITTER = "twitter"


class NodeType(str, Enum):
    VALIDATOR = "validator"
    MINER = "miner"


class Node(BaseModel):
    hotkey: str
    netuid: int
    node_type: NodeType
    metadata: dict[str, Any] = Field(default_factory=dict)

    # Relationships - optional since we don't always load them
    social_accounts: Optional[list["SocialAccount"]] = None


class SocialAccount(BaseModel):
    platform_type: str
    account_id: str
    username: str
    node_hotkey: Optional[str] = None
    node_netuid: Optional[int] = None
    extra_data: dict[str, Any] = Field(
        default_factory=dict,
        description="Extra data for the social account, come from platform 's object model",
    )


class ProcessingStatus(str, Enum):
    NEW = "new"
    PROCESSED = "processed"
    REJECTED = "rejected"
    SCORED = "scored"


class Post(BaseModel):
    id: Optional[int] = None
    platform_id: str = Field(..., description="The platform provided ID of the post")
    platform_type: PlatformType
    content: str
    account_id: int
    topics: Optional[list[str]] = Field(
        default=None,
        description="The topics that the post is about, come from the topic tagging process",
    )
    extra_data: dict[str, Any] = Field(
        default_factory=dict,
        description="Extra data for the post, come from platform 's object model",
    )
    processing_status: ProcessingStatus = ProcessingStatus.NEW
    processing_note: Optional[str] = Field(
        default=None,
        description="Notes about the processing of the post, for debugging purposes, contain rejection reasons if the post was rejected",
    )

    # Relationships
    interactions: Optional[list["Interaction"]] = None


class InteractionType(str, Enum):
    LIKE = "like"
    REPLY = "reply"
    SHARE = "share"


class Interaction(BaseModel):
    id: Optional[int] = None
    platform_id: str = Field(
        ..., description="The platform provided ID of the interaction"
    )
    platform_type: PlatformType
    interaction_type: InteractionType
    account_id: int = Field(..., description="The ID of the account that interacted")
    post_id: int = Field(..., description="The ID of the post that got interacted with")
    content: Optional[str] = None
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Extra data for the interaction, come from platform 's object model",
    )
    processing_status: ProcessingStatus = ProcessingStatus.PENDING
    score: Optional[float] = None
