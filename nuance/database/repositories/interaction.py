# database/repositories/interaction.py
import datetime
from typing import Optional

import sqlalchemy as sa

from nuance.database.schema import Interaction as InteractionORM
from nuance.database.schema import Post as PostORM
from nuance.models import Interaction, ProcessingStatus
from nuance.database.repositories.base import BaseRepository

class InteractionRepository(BaseRepository[InteractionORM, Interaction]):
    def __init__(self, session_factory):
        super().__init__(InteractionORM, session_factory)
    
    @classmethod
    def _orm_to_domain(cls, orm_obj: InteractionORM) -> Interaction:
        return Interaction(
            platform_id=orm_obj.interaction_id,
            interaction_type=orm_obj.interaction_type,
            post_id=orm_obj.post_id,
            content=orm_obj.content,
            extra_data=orm_obj.extra_data,
            processing_status=orm_obj.processing_status,
            created_at=orm_obj.created_at,
        )
    
    @classmethod
    def _domain_to_orm(cls, domain_obj: Interaction) -> InteractionORM:
        return InteractionORM(
            interaction_id=domain_obj.interaction_id,
            interaction_type=domain_obj.interaction_type,
            post_id=domain_obj.post_id,
            content=domain_obj.content,
            extra_data=domain_obj.extra_data,
            processing_status=domain_obj.processing_status,
            created_at=domain_obj.created_at,
        )
        
    async def get_recent_interactions(self, since_date: datetime.datetime) -> list[Interaction]:
        """
        Get all processed interactions since the given date.
        
        Args:
            since_date: Only include interactions newer than this date
            
        Returns:
            List of processed interactions
        """
        async with self.session_factory() as session:
            result = await session.execute(
                sa.select(InteractionORM)
                .where(
                    InteractionORM.processing_status == "processed",
                    InteractionORM.created_at >= since_date
                )
                .order_by(InteractionORM.created_at.desc())
            )
            
            return [self._orm_to_domain(obj) for obj in result.scalars().all()]
    
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
            return [self._orm_to_domain(obj) for obj in result.scalars().all()]