# database/repositories/interaction.py
from typing import Optional

import sqlalchemy as sa

from nuance.database.schema import Interaction as InteractionORM
from nuance.database.schema import Post as PostORM
from nuance.models import Interaction, ProcessingStatus
from nuance.database.repositories.base import BaseRepository

class InteractionRepository(BaseRepository[InteractionORM, Interaction]):
    def __init__(self, session_factory):
        super().__init__(InteractionORM, session_factory)
    
    def _to_domain(self, orm_obj: InteractionORM) -> Interaction:
        return Interaction(
            id=orm_obj.id,
            platform_id=orm_obj.platform_id,
            interaction_type=orm_obj.interaction_type,
            post_id=orm_obj.post_id,
            content=orm_obj.content,
            metadata=orm_obj.metadata,
            processing_status=orm_obj.processing_status,
            score=orm_obj.score,
            created_at=orm_obj.created_at,
            updated_at=orm_obj.updated_at
        )
    
    def _to_orm(self, domain_obj: Interaction) -> InteractionORM:
        return InteractionORM(
            id=domain_obj.id,
            platform_id=domain_obj.platform_id,
            interaction_type=domain_obj.interaction_type,
            post_id=domain_obj.post_id,
            content=domain_obj.content,
            metadata=domain_obj.metadata,
            processing_status=domain_obj.processing_status,
            score=domain_obj.score
        )
    
    async def get_pending_interactions_for_processed_posts(self, limit: int = 100) -> list[Interaction]:
        async with self.session_factory() as session:
            result = await session.execute(
                sa.select(InteractionORM)
                .join(PostORM, InteractionORM.post_id == PostORM.id)
                .where(
                    InteractionORM.processing_status == ProcessingStatus.PENDING,
                    PostORM.processing_status == ProcessingStatus.PROCESSED
                )
                .limit(limit)
            )
            return [self._to_domain(obj) for obj in result.scalars().all()]
    
    async def update_score(self, interaction_id: int, score: float) -> bool:
        async with self.session_factory() as session:
            result = await session.execute(
                sa.update(InteractionORM)
                .where(InteractionORM.id == interaction_id)
                .values(score=score, processing_status=ProcessingStatus.SCORED)
                .returning(InteractionORM)
            )
            return result.rowcount > 0