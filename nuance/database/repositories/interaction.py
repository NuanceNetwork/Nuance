# database/repositories/interaction.py
import datetime

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert

from nuance.database.schema import Interaction as InteractionORM
from nuance.models import Interaction, ProcessingStatus
from nuance.database.repositories.base import BaseRepository


class InteractionRepository(BaseRepository[InteractionORM, Interaction]):
    def __init__(self, session_factory):
        super().__init__(InteractionORM, session_factory)

    @classmethod
    def _orm_to_domain(cls, orm_obj: InteractionORM) -> Interaction:
        return Interaction(
            interaction_id=orm_obj.interaction_id,
            platform_type=orm_obj.platform_type,
            interaction_type=orm_obj.interaction_type,
            account_id=orm_obj.account_id,
            post_id=orm_obj.post_id,
            content=orm_obj.content,
            created_at=orm_obj.created_at,
            extra_data=orm_obj.extra_data,
            processing_status=orm_obj.processing_status,
            processing_note=orm_obj.processing_note
        )

    @classmethod
    def _domain_to_orm(cls, domain_obj: Interaction) -> InteractionORM:
        return InteractionORM(
            interaction_id=domain_obj.interaction_id,
            platform_type=domain_obj.platform_type,
            interaction_type=domain_obj.interaction_type,
            account_id=domain_obj.account_id,
            post_id=domain_obj.post_id,
            content=domain_obj.content,
            created_at=domain_obj.created_at,
            extra_data=domain_obj.extra_data,
            processing_status=domain_obj.processing_status,
            processing_note=domain_obj.processing_note
        )

    async def get_recent_interactions(
        self, since_date: datetime.datetime, processing_status: ProcessingStatus = None
    ) -> list[Interaction]:
        """
        Get all processed interactions since the given date.

        Args:
            since_date: Only include interactions newer than this date

        Returns:
            List of processed interactions
        """
        async with self.session_factory() as session:
            query = sa.select(InteractionORM).where(
                InteractionORM.created_at >= since_date
            )
            if processing_status is not None:
                query = query.where(InteractionORM.processing_status == processing_status)
            result = await session.execute(
                query.order_by(InteractionORM.created_at.desc())
            )
            all_object = [obj for obj in result.scalars().all()]
            return [self._orm_to_domain(obj) for obj in all_object]

    async def upsert(
        self,
        entity: Interaction,
        exclude_none_updates: bool = False,
        exclude_empty_updates: bool = False,
    ) -> Interaction:
        async with self.session_factory() as session:
            # Create values dictionary with all fields
            values_dict = {
                "platform_type": entity.platform_type,
                "interaction_id": entity.interaction_id,
                "interaction_type": entity.interaction_type,
                "account_id": entity.account_id,
                "post_id": entity.post_id,
                "content": entity.content,
                "created_at": entity.created_at,
                "extra_data": entity.extra_data,
                "processing_status": entity.processing_status,
                "processing_note": entity.processing_note,
            }

            # Define primary key fields to exclude from updates
            primary_key_fields = ["platform_type", "interaction_id"]

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
                pg_insert(InteractionORM)
                .values(values_dict)
                .on_conflict_do_update(
                    constraint="uq_platform_type_interaction_id", set_=update_dict
                )
            )

            # Execute the statement
            await session.execute(stmt)
            await session.commit()

            # Fetch the inserted/updated record
            result = await session.execute(
                sa.select(InteractionORM).where(
                    InteractionORM.platform_type == entity.platform_type,
                    InteractionORM.interaction_id == entity.interaction_id,
                )
            )
            updated_orm_interaction = result.scalars().first()

            return self._orm_to_domain(updated_orm_interaction)
