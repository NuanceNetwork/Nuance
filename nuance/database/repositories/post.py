# database/repositories/post.py
from typing import Optional, List
import sqlalchemy as sa

from nuance.database.schema import Post as PostORM
from nuance.models import Post, ProcessingStatus
from nuance.database.repositories.base import BaseRepository

class PostRepository(BaseRepository[PostORM, Post]):
    def __init__(self, session_factory):
        super().__init__(PostORM, session_factory)
    
    def _to_domain(self, orm_obj: PostORM) -> Post:
        return Post(
            id=orm_obj.id,
            platform_id=orm_obj.platform_id,
            platform_type=orm_obj.platform_type,
            content=orm_obj.content,
            account_id=orm_obj.account_id,
            extra_data=orm_obj.extra_data,
            processing_status=orm_obj.processing_status,
            created_at=orm_obj.created_at,
            updated_at=orm_obj.updated_at
        )
    
    def _to_orm(self, domain_obj: Post) -> PostORM:
        return PostORM(
            id=domain_obj.id,
            platform_id=domain_obj.platform_id,
            platform_type=domain_obj.platform_type,
            content=domain_obj.content,
            account_id=domain_obj.account_id,
            extra_data=domain_obj.extra_data,
            processing_status=domain_obj.processing_status
        )
    
    async def get_by_platform_id(
        self, platform_type: str, platform_id: str
    ) -> Optional[Post]:
        async with self.session_factory() as session:
            result = await session.execute(
                sa.select(PostORM).where(
                    PostORM.platform_type == platform_type,
                    PostORM.platform_id == platform_id
                )
            )
            orm_post = result.scalars().first()
            return self._orm_to_domain(orm_post) if orm_post else None
    
    async def get_pending_posts(self, limit: int = 100) -> List[Post]:
        async with self.session_factory() as session:
            result = await session.execute(
                sa.select(PostORM)
                .where(PostORM.processing_status == ProcessingStatus.PENDING)
                .limit(limit)
            )
            return [self._orm_to_domain(obj) for obj in result.scalars().all()]
    
    async def update_status(self, post_id: int, status: ProcessingStatus) -> bool:
        async with self.session_factory() as session:
            result = await session.execute(
                sa.update(PostORM)
                .where(PostORM.id == post_id)
                .values(processing_status=status)
                .returning(PostORM)
            )
            return result.rowcount > 0