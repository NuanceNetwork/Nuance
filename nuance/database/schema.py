import datetime
from typing import Optional

import sqlalchemy as sa
from sqlalchemy.orm import (
    declarative_base,
    DeclarativeBase,
    mapped_column,
    Mapped,
    relationship,
)

from nuance.models import PlatformType, ProcessingStatus, InteractionType

Base: DeclarativeBase = declarative_base()


class TimestampMixin:
    """Mixin that adds timestamp columns to models."""

    __abstract__ = True

    _record_created_at: Mapped[datetime.datetime] = mapped_column(
        sa.DateTime(timezone=True),
        default=datetime.datetime.now(tz=datetime.timezone.utc),
        nullable=False,
    )
    _record_updated_at: Mapped[datetime.datetime] = mapped_column(
        sa.DateTime(timezone=True),
        default=datetime.datetime.now(tz=datetime.timezone.utc),
        onupdate=datetime.datetime.now(tz=datetime.timezone.utc),
        nullable=False,
    )


class Node(Base, TimestampMixin):
    __tablename__ = "nodes"

    node_hotkey: Mapped[str] = mapped_column(
        sa.String, primary_key=True, nullable=False
    )
    node_netuid: Mapped[int] = mapped_column(
        sa.Integer, primary_key=True, nullable=False
    )

    # Relationships
    social_accounts: Mapped[list["SocialAccount"]] = relationship(back_populates="node")

    __table_args__ = (
        sa.UniqueConstraint(
            "node_hotkey", "node_netuid", name="uq_node_hotkey_node_netuid"
        ),
    )


class SocialAccount(Base, TimestampMixin):
    __tablename__ = "social_accounts"

    platform_type: Mapped[str] = mapped_column(
        sa.Enum(
            PlatformType,
            name="platform_type_enum",
            validate_strings=True,
        ),
        nullable=False,
        primary_key=True,
    )  # 'twitter', 'facebook', etc.
    account_id: Mapped[str] = mapped_column(sa.String, nullable=False, primary_key=True)
    account_username: Mapped[Optional[str]] = mapped_column(sa.String, nullable=True)
    node_hotkey: Mapped[Optional[str]] = mapped_column(sa.String, nullable=True)
    node_netuid: Mapped[Optional[int]] = mapped_column(sa.Integer, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False
    )
    extra_data: Mapped[dict] = mapped_column(
        sa.JSON, default={}
    )  # Store platform-specific data here

    # Relationships
    node: Mapped["Node"] = relationship(back_populates="social_accounts")
    posts: Mapped[list["Post"]] = relationship(back_populates="social_account")
    interactions: Mapped[list["Interaction"]] = relationship(
        back_populates="social_account"
    )

    __table_args__ = (
        sa.UniqueConstraint(
            "platform_type", "account_id", name="uq_platform_type_account_id"
        ),
        sa.ForeignKeyConstraint(
            ["node_hotkey", "node_netuid"],
            ["nodes.node_hotkey", "nodes.node_netuid"],
        ),
    )


class Post(Base, TimestampMixin):
    __tablename__ = "posts"

    platform_type: Mapped[str] = mapped_column(
        sa.Enum(
            PlatformType,
            name="platform_type_enum",
            validate_strings=True,
        ),
        nullable=False,
        primary_key=True,
    )  # 'twitter', 'facebook', etc.
    post_id: Mapped[str] = mapped_column(
        sa.String, nullable=False, primary_key=True
    )  # Original ID on platform
    account_id: Mapped[str] = mapped_column(
        sa.String
    )  # Account ID of the social account that posted this post
    content: Mapped[str] = mapped_column(sa.Text, default="")
    topics: Mapped[list[str]] = mapped_column(sa.JSON, default=[])
    created_at: Mapped[datetime.datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False
    )
    extra_data: Mapped[dict] = mapped_column(
        sa.JSON, default={}
    )  # Platform-specific post data
    processing_status: Mapped[str] = mapped_column(
        sa.Enum(
            ProcessingStatus,
            name="processing_status_enum",
            validate_strings=True,
        ),
        default=ProcessingStatus.NEW,
    )
    processing_note: Mapped[str] = mapped_column(sa.Text, nullable=True)

    # Relationships
    social_account: Mapped["SocialAccount"] = relationship(
        back_populates="posts", foreign_keys="[Post.platform_type, Post.account_id]"
    )
    interactions: Mapped[list["Interaction"]] = relationship(
        back_populates="post", overlaps="interactions"
    )

    __table_args__ = (
        sa.UniqueConstraint(
            "platform_type", "post_id", name="uq_platform_type_post_id"
        ),
        sa.ForeignKeyConstraint(
            ["platform_type", "account_id"],
            ["social_accounts.platform_type", "social_accounts.account_id"],
        ),
    )


class Interaction(Base, TimestampMixin):
    __tablename__ = "interactions"

    platform_type: Mapped[str] = mapped_column(
        sa.Enum(
            PlatformType,
            name="platform_type_enum",
            validate_strings=True,
        ),
        nullable=False,
        primary_key=True,
    )  # 'twitter', 'facebook', etc.
    interaction_id: Mapped[str] = mapped_column(
        sa.String,
        nullable=False,
        primary_key=True,
    )
    interaction_type: Mapped[str] = mapped_column(
        sa.Enum(
            InteractionType,
            name="interaction_type_enum",
            validate_strings=True,
        ),
        nullable=False,
    )
    account_id: Mapped[str] = mapped_column(
        sa.String
    )  # Account ID of the social account that interacted with this post
    post_id: Mapped[str] = mapped_column(
        sa.String
    )  # Post ID of the post that was interacted with
    content: Mapped[Optional[str]] = mapped_column(sa.Text, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False
    )
    extra_data: Mapped[dict] = mapped_column(
        sa.JSON, default={}
    )  # Platform-specific and interaction-specific data
    processing_status: Mapped[str] = mapped_column(
        sa.Enum(
            ProcessingStatus,
            name="processing_status_enum",
            validate_strings=True,
        ),
        default=ProcessingStatus.NEW,
    )
    processing_note: Mapped[str] = mapped_column(sa.Text, nullable=True)

    # Relationships
    social_account: Mapped["SocialAccount"] = relationship(
        back_populates="interactions",
        foreign_keys="[Interaction.platform_type, Interaction.account_id]",
        overlaps="interactions",
    )
    post: Mapped["Post"] = relationship(
        back_populates="interactions",
        foreign_keys="[Interaction.platform_type, Interaction.post_id]",
        overlaps="interactions,social_account",
    )

    __table_args__ = (
        sa.UniqueConstraint(
            "platform_type", "interaction_id", name="uq_platform_type_interaction_id"
        ),
        sa.ForeignKeyConstraint(
            ["platform_type", "post_id"],
            ["posts.platform_type", "posts.post_id"],
        ),
        sa.ForeignKeyConstraint(
            ["platform_type", "account_id"],
            ["social_accounts.platform_type", "social_accounts.account_id"],
        ),
    )
