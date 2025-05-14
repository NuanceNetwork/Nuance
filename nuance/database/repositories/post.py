# database/repositories/post.py
import datetime
from typing import Optional

import sqlalchemy as sa
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from nuance.database.schema import Post as PostORM
from nuance.models import Post, ProcessingStatus
from nuance.database.repositories.base import BaseRepository


class PostRepository(BaseRepository[PostORM, Post]):
    def __init__(self, session_factory):
        super().__init__(PostORM, session_factory)

    @classmethod
    def _orm_to_domain(cls, orm_obj: PostORM) -> Post:
        return Post(
            platform_type=orm_obj.platform_type,
            post_id=orm_obj.post_id,
            account_id=orm_obj.account_id,
            content=orm_obj.content,
            topics=orm_obj.topics,
            created_at=orm_obj.created_at,
            extra_data=orm_obj.extra_data,
            processing_status=orm_obj.processing_status,
            processing_note=orm_obj.processing_note,
        )

    @classmethod
    def _domain_to_orm(cls, domain_obj: Post) -> PostORM:
        return PostORM(
            platform_type=domain_obj.platform_type,
            post_id=domain_obj.post_id,
            account_id=domain_obj.account_id,
            content=domain_obj.content,
            topics=domain_obj.topics,
            created_at=domain_obj.created_at,
            extra_data=domain_obj.extra_data,
            processing_status=domain_obj.processing_status,
            processing_note=domain_obj.processing_note,
        )

    async def get_by_platform_id(
        self, platform_type: str, post_id: str
    ) -> Optional[Post]:
        async with self.session_factory() as session:
            result = await session.execute(
                sa.select(PostORM).where(
                    PostORM.platform_type == platform_type, PostORM.post_id == post_id
                )
            )
            orm_post = result.scalars().first()
            return self._orm_to_domain(orm_post) if orm_post else None

    async def get_recent_posts(
        self, cutoff_date: datetime.datetime, **filters
    ) -> list[Post]:
        """
        Get posts created on or after the cutoff date, with optional additional filters.

        Args:
            cutoff_date: Timezone-aware datetime to filter posts (should be in UTC)
            **filters: Additional filters to apply (e.g., platform_type, account_id)

        Returns:
            List of Post domain objects sorted by creation date (newest first)
        """
        async with self.session_factory() as session:
            query = sa.select(PostORM).where(PostORM.created_at >= cutoff_date)

            # Apply additional filters
            for field, value in filters.items():
                query = query.filter(getattr(PostORM, field) == value)

            # Order by created_at, newest first
            query = query.order_by(PostORM.created_at.desc())

            result = await session.execute(query)
            orm_posts = result.scalars().all()

            return [self._orm_to_domain(post) for post in orm_posts]

    async def update_status(self, post_id: int, status: ProcessingStatus) -> bool:
        async with self.session_factory() as session:
            result = await session.execute(
                sa.update(PostORM)
                .where(PostORM.id == post_id)
                .values(processing_status=status)
                .returning(PostORM)
            )
            return result.rowcount > 0

    async def upsert(
        self,
        entity: Post,
        exclude_none_updates: bool = False,
        exclude_empty_updates: bool = False,
    ) -> Post:
        async with self.session_factory() as session:
            # Create values dictionary with all fields
            values_dict = {
                "platform_type": entity.platform_type,
                "post_id": entity.post_id,
                "account_id": entity.account_id,
                "content": entity.content,
                "topics": entity.topics,
                "created_at": entity.created_at,
                "extra_data": entity.extra_data,
                "processing_status": entity.processing_status,
                "processing_note": entity.processing_note,
            }

            # Define primary key fields to exclude from updates
            primary_key_fields = ["platform_type", "post_id"]

            # Create update dictionary
            update_dict = {
                k: v for k, v in values_dict.items() if k not in primary_key_fields
            }
            if exclude_none_updates:
                # Filter out None values and primary keys
                update_dict = {k: v for k, v in update_dict.items() if v is not None}
            if exclude_empty_updates:
                # Filter out empty values
                update_dict = {k: v for k, v in update_dict.items() if bool(v)}

            stmt = (
                sqlite_insert(PostORM)
                .values(values_dict)
                .on_conflict_do_update(
                    # constraint="uq_platform_type_post_id",
                    index_elements=["platform_type", "post_id"],
                    index_where=sa.and_(
                        PostORM.platform_type == entity.platform_type,
                        PostORM.post_id == entity.post_id,
                    ),
                    set_=update_dict,
                )
            )

            # Execute the statement
            await session.execute(stmt)
            await session.commit()

            # Fetch the inserted/updated record
            result = await session.execute(
                sa.select(PostORM).where(
                    PostORM.platform_type == entity.platform_type,
                    PostORM.post_id == entity.post_id,
                )
            )
            updated_orm_post = result.scalars().first()

            return self._orm_to_domain(updated_orm_post)
