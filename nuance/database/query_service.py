from datetime import datetime

import sqlalchemy as sa

from nuance.models import Node, SocialAccount, Post, Interaction
from nuance.database.schema import (
    Interaction as InteractionORM,
    Post as PostORM,
    SocialAccount as SocialAccountORM,
)
from nuance.database.repositories import (
    InteractionRepository,
    SocialAccountRepository,
    PostRepository,
)


class QueryService:
    """Service for complex queries that span multiple aggregates."""

    def __init__(self, session_factory):
        self.session_factory = session_factory

    async def get_recent_interactions_with_miners(
        self, since_date: datetime
    ) -> list[tuple[Node, Interaction]]:
        """
        Get all processed interactions since the given date, joined with miner data.

        Returns a list of dictionaries containing joined data across aggregates.
        """
        async with self.session_factory() as session:
            # Complex join query across multiple aggregates
            stmt = (
                sa.select(
                    InteractionORM,
                    PostORM,
                    SocialAccountORM.alias("post_account"),
                    SocialAccountORM.alias("interaction_account"),
                )
                .join(PostORM, InteractionORM.post_id == PostORM.post_id)
                .join(
                    SocialAccountORM.alias("post_account"),
                    sa.and_(
                        PostORM.platform_type
                        == SocialAccountORM.alias("post_account").platform_type,
                        PostORM.account_id
                        == SocialAccountORM.alias("post_account").account_id,
                    ),
                )
                .join(
                    SocialAccountORM.alias("interaction_account"),
                    sa.and_(
                        InteractionORM.platform_type
                        == SocialAccountORM.alias("interaction_account").platform_type,
                        InteractionORM.account_id
                        == SocialAccountORM.alias("interaction_account").account_id,
                    ),
                )
                .where(
                    InteractionORM.processing_status == "processed",
                    InteractionORM.created_at >= since_date,
                )
                .order_by(InteractionORM.created_at.desc())
            )

            result = await session.execute(stmt)

            # Process results
            joined_data = []
            for (
                interaction_orm,
                post_orm,
                post_account_orm,
                interaction_account_orm,
            ) in result:
                joined_data.append(
                    {
                        "interaction": InteractionRepository._orm_to_domain(
                            interaction_orm
                        ),
                        "post": PostRepository._orm_to_domain(post_orm),
                        "post_account": SocialAccountRepository._orm_to_domain(
                            post_account_orm
                        ),
                        "interaction_account": SocialAccountRepository._orm_to_domain(
                            interaction_account_orm
                        ),
                    }
                )

            return joined_data