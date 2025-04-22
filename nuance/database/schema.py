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

Base: DeclarativeBase = declarative_base()


class TimestampMixin(Base):
    __abstract__ = True

    _record_created_at: Mapped[datetime.datetime] = mapped_column(
        sa.DateTime,
        default=datetime.datetime.now(tz=datetime.timezone.utc),
        nullable=False,
    )
    _record_updated_at: Mapped[datetime.datetime] = mapped_column(
        sa.DateTime,
        default=datetime.datetime.now(tz=datetime.timezone.utc),
        onupdate=datetime.datetime.now(tz=datetime.timezone.utc),
        nullable=False,
    )


class Node(Base, TimestampMixin):
    __tablename__ = "nodes"

    hotkey: Mapped[str] = mapped_column(sa.String, primary_key=True, nullable=False)
    netuid: Mapped[int] = mapped_column(sa.Integer, primary_key=True, nullable=False)
    node_type: Mapped[str] = mapped_column(
        sa.Enum("validator", "miner"), nullable=False
    )

    # Relationships
    # social_accounts: Mapped[list["SocialAccount"]] = relationship(back_populates="node")


class SocialAccount(Base, TimestampMixin):
    __tablename__ = "social_accounts"

    platform_type: Mapped[str] = mapped_column(
        sa.String, nullable=False, primary_key=True
    )  # 'twitter', 'facebook', etc.
    account_id: Mapped[str] = mapped_column(sa.String, nullable=False, primary_key=True)
    username: Mapped[str] = mapped_column(sa.String)
    created_at: Mapped[datetime.datetime] = mapped_column(sa.DateTime, nullable=True)
    node_hotkey: Mapped[Optional[str]] = mapped_column(
        sa.String, sa.ForeignKey("nodes.hotkey"), nullable=True
    )
    extra_data: Mapped[dict] = mapped_column(
        sa.JSON
    )  # Store platform-specific data here

    # Relationships
    node: Mapped["Node"] = relationship(back_populates="social_accounts")


class Post(Base, TimestampMixin):
    __tablename__ = "posts"

    platform_type: Mapped[str] = mapped_column(
        sa.String, nullable=False, primary_key=True
    )  # 'twitter', 'facebook', etc.
    post_id: Mapped[str] = mapped_column(
        sa.String, nullable=False, primary_key=True
    )  # Original ID on platform
    account_id: Mapped[int] = mapped_column(
        sa.Integer, sa.ForeignKey("social_accounts.account_id")
    )  # Account ID of the social account that posted this post
    content: Mapped[str] = mapped_column(sa.Text)
    topics: Mapped[list[str]] = mapped_column(sa.JSON)
    created_at: Mapped[datetime.datetime] = mapped_column(sa.DateTime, nullable=True)
    extra_data: Mapped[dict] = mapped_column(sa.JSON)  # Platform-specific post data
    processing_status: Mapped[str] = mapped_column(
        sa.Enum("new", "processed", "rejected"), default="new"
    )

    # Relationships
    social_account: Mapped["SocialAccount"] = relationship(back_populates="posts")
    interactions: Mapped[list["Interaction"]] = relationship(back_populates="post")


class Interaction(Base, TimestampMixin):
    __tablename__ = "interactions"

    platform_type: Mapped[str] = mapped_column(
        sa.String,
        nullable=False,
        primary_key=True,
    )  # 'twitter', 'facebook', etc.
    interaction_type: Mapped[str] = mapped_column(
        sa.Enum("like", "comment", "share", "follow", "unfollow"), nullable=False
    )
    interaction_id: Mapped[str] = mapped_column(sa.String, nullable=False)
    account_id: Mapped[int] = mapped_column(
        sa.Integer, sa.ForeignKey("social_accounts.account_id")
    )  # Account ID of the social account that interacted with this post
    post_id: Mapped[int] = mapped_column(
        sa.Integer, sa.ForeignKey("posts.post_id")
    )  # Post ID of the post that was interacted with
    content: Mapped[str] = mapped_column(sa.Text, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(sa.DateTime, nullable=True)
    extra_data: Mapped[dict] = mapped_column(
        sa.JSON
    )  # Platform-specific and interaction-specific data
    processing_status: Mapped[str] = mapped_column(
        sa.Enum("new", "processed", "rejected"), default="new"
    )

    # Relationships
    post: Mapped["Post"] = relationship(back_populates="interactions")
