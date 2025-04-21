import datetime
from typing import Any

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

    created_at: Mapped[datetime.datetime] = mapped_column(
        sa.DateTime,
        default=datetime.datetime.now(tz=datetime.timezone.utc),
        nullable=False,
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
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
    metadata: Mapped[dict] = mapped_column(sa.JSON)

    social_accounts: Mapped[list["SocialAccount"]] = relationship(back_populates="node")


class SocialAccount(Base, TimestampMixin):
    __tablename__ = "social_accounts"

    id: Mapped[int] = mapped_column(sa.Integer, primary_key=True)
    platform_type: Mapped[str] = mapped_column(
        sa.String, nullable=False
    )  # 'twitter', 'facebook', etc.
    account_id: Mapped[str] = mapped_column(sa.String, nullable=False)
    username: Mapped[str] = mapped_column(sa.String)
    node_id: Mapped[str] = mapped_column(sa.String, sa.ForeignKey("nodes.hotkey"))
    extra_data: Mapped[dict] = mapped_column(
        sa.JSON
    )  # Store platform-specific data here

    node: Mapped["Node"] = relationship(back_populates="social_accounts")


class Post(Base, TimestampMixin):
    __tablename__ = 'posts'
    
    id: Mapped[int] = mapped_column(sa.Integer, primary_key=True)
    platform_id: Mapped[str] = mapped_column(sa.String, nullable=False)  # Original ID on platform
    platform_type: Mapped[str] = mapped_column(sa.String, nullable=False)
    content: Mapped[str] = mapped_column(sa.Text)
    account_id: Mapped[int] = mapped_column(sa.Integer, sa.ForeignKey('social_accounts.id'))
    extra_data: Mapped[dict] = mapped_column(sa.JSON)  # Platform-specific post data
    processing_status: Mapped[str] = mapped_column(sa.String, default="pending")
    
    interactions: Mapped[list["Interaction"]] = relationship(back_populates="post")
    
    
class Interaction(Base, TimestampMixin):
    __tablename__ = "interactions"

    id: Mapped[int] = mapped_column(sa.Integer, primary_key=True)
    platform_id: Mapped[str] = mapped_column(sa.String, nullable=False)
    interaction_type: Mapped[str] = mapped_column(sa.String, nullable=False)
    post_id: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    extra_data: Mapped[dict] = mapped_column(sa.JSON) # Platform-specific and interaction-specific data
    post: Mapped["Post"] = relationship(back_populates="interactions")
