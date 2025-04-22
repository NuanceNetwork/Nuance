# nuance/models/models.py
from enum import Enum
import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


class PlatformType(str, Enum):
    TWITTER = "twitter"


class Commit(BaseModel):
    uid: int
    hotkey: str
    platform: PlatformType
    account_id: Optional[str] = None
    username: str
    verification_post_id: str


class Node(BaseModel):
    hotkey: str
    netuid: int

    # Relationships - optional since we don't always load them
    social_accounts: Optional[list["SocialAccount"]] = None


class SocialAccount(BaseModel):
    platform_type: str
    account_id: str
    username: str
    created_at: Optional[datetime.datetime] = None
    node_hotkey: Optional[str] = None
    extra_data: dict[str, Any] = Field(
        default_factory=dict,
        description="Extra data for the social account, come from platform 's object model",
    )


class ProcessingStatus(str, Enum):
    NEW = "new"             # New and has not been processed yet
    ACCEPTED = "accepted"   # Processed and has been accepted
    REJECTED = "rejected"   # Processed and has been rejected
    ERROR = "error"         # Error in processing, may retry later


class Post(BaseModel):
    post_id: str = Field(..., description="The platform provided ID of the post")
    platform_type: PlatformType
    content: str
    account_id: int
    content_type: Optional[str] = Field(
        default=None,
        description="Content of the post, this is now the text of the post",
    )
    topics: Optional[list[str]] = Field(
        default=None,
        description="The topics that the post is about, come from the topic tagging process",
    )
    created_at: Optional[datetime.datetime] = None
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
    REPLY = "reply"


class Interaction(BaseModel):
    interaction_id: str = Field(
        ..., description="The platform provided ID of the interaction"
    )
    platform_type: PlatformType
    interaction_type: InteractionType
    account_id: int = Field(..., description="The ID of the account that interacted")
    post_id: int = Field(..., description="The ID of the post that got interacted with")
    content: Optional[str] = None
    created_at: Optional[datetime.datetime] = None
    extra_data: dict[str, Any] = Field(
        default_factory=dict,
        description="Extra data for the interaction, come from platform 's object model",
    )
    processing_status: ProcessingStatus = ProcessingStatus.NEW
    processing_note: Optional[str] = Field(
        default=None,
        description="Notes about the processing of the interaction, for debugging purposes, contain rejection reasons if the interaction was rejected",
    )
    
    # Relationships
    social_account: Optional["SocialAccount"] = None
    post: Optional["Post"] = None
