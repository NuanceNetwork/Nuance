# nuance/models/models.py
from enum import Enum
import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


class PlatformType(str, Enum):
    TWITTER = "twitter"
    
    
class ProcessingStatus(str, Enum):
    NEW = "new"  # New and has not been processed yet
    ACCEPTED = "accepted"  # Processed and has been accepted
    REJECTED = "rejected"  # Processed and has been rejected
    ERROR = "error"  # Error in processing, may retry later


class InteractionType(str, Enum):
    REPLY = "reply"


class Commit(BaseModel):
    uid: int
    hotkey: str
    platform: PlatformType
    account_id: Optional[str] = None
    username: str
    verification_post_id: str


# Domain models
# These are the models that are used in the domain layer
# All the fields that are primary keys are required
# Relationships are optional and we don't always load them, be careful with these fields, they can create infinite recursion

class Node(BaseModel):
    node_hotkey: str
    node_netuid: int

    # Relationships
    social_accounts: Optional[list["SocialAccount"]] = None


class SocialAccount(BaseModel):
    platform_type: str
    account_id: str
    account_username: Optional[str] = None
    node_hotkey: Optional[str] = None
    node_netuid: Optional[int] = None
    created_at: datetime.datetime
    extra_data: dict[str, Any] = Field(
        default={},
        description="Extra data for the social account, come from platform 's object model",
    )

    # Relationships
    node: Optional["Node"] = None
    posts: Optional[list["Post"]] = None
    interactions: Optional[list["Interaction"]] = None


class Post(BaseModel):
    platform_type: PlatformType
    post_id: str = Field(..., description="The platform provided ID of the post")
    account_id: str
    content: str = Field(
        default="",
        description="Content of the post, this is now the text of the post",
    )
    topics: list[str] = Field(
        default=[],
        description="The topics that the post is about, come from the topic tagging process",
    )
    created_at: datetime.datetime
    extra_data: dict[str, Any] = Field(
        default={},
        description="Extra data for the post, come from platform 's object model",
    )
    processing_status: ProcessingStatus = ProcessingStatus.NEW
    processing_note: Optional[str] = Field(
        default=None,
        description="Notes about the processing of the post, for debugging purposes, contain rejection reasons if the post was rejected",
    )

    # Relationships
    social_account: Optional["SocialAccount"] = None
    interactions: Optional[list["Interaction"]] = None


class Interaction(BaseModel):
    interaction_id: str = Field(
        ..., description="The platform provided ID of the interaction"
    )
    platform_type: PlatformType
    interaction_type: InteractionType
    account_id: str = Field(..., description="The ID of the account that interacted")
    post_id: str = Field(..., description="The ID of the post that got interacted with")
    content: Optional[str] = None
    created_at: datetime.datetime
    extra_data: dict[str, Any] = Field(
        default={},
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
