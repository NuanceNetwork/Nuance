# database/repositories/social_account.py
from typing import Optional, List

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from nuance.database.schema import SocialAccount as SocialAccountORM
from nuance.models import SocialAccount
from nuance.database.repositories.base import BaseRepository


class SocialAccountRepository(BaseRepository[SocialAccountORM, SocialAccount]):
    def __init__(self, session_factory):
        super().__init__(SocialAccountORM, session_factory)

    @classmethod
    def _orm_to_domain(cls, orm_obj: SocialAccountORM) -> SocialAccount:
        return SocialAccount(
            platform_type=orm_obj.platform_type,
            account_id=orm_obj.account_id,
            account_username=orm_obj.account_username,
            created_at=orm_obj.created_at,
            node_hotkey=orm_obj.node_hotkey,
            node_netuid=orm_obj.node_netuid,
            extra_data=orm_obj.extra_data,
        )

    @classmethod
    def _domain_to_orm(cls, domain_obj: SocialAccount) -> SocialAccountORM:
        return SocialAccountORM(
            platform_type=domain_obj.platform_type,
            account_id=domain_obj.account_id,
            account_username=domain_obj.account_username,
            node_hotkey=domain_obj.node_hotkey,
            node_netuid=domain_obj.node_netuid,
            extra_data=domain_obj.extra_data,
        )

    async def get_by_platform_id(
        self, platform_type: str, account_id: str
    ) -> Optional[SocialAccount]:
        async with self.session_factory() as session:
            result = await session.execute(
                select(SocialAccountORM).where(
                    SocialAccountORM.platform_type == platform_type,
                    SocialAccountORM.account_id == account_id,
                )
            )
            orm_account = result.scalars().first()
            return self._orm_to_domain(orm_account) if orm_account else None

    async def get_by_node(self, node_hotkey: str) -> List[SocialAccount]:
        async with self.session_factory() as session:
            result = await session.execute(
                select(SocialAccountORM).where(
                    SocialAccountORM.node_hotkey == node_hotkey
                )
            )
            return [self._orm_to_domain(obj) for obj in result.scalars().all()]

    async def upsert(
        self,
        entity: SocialAccount,
        exclude_none_updates: bool = False,
        exclude_empty_updates: bool = False,
    ) -> SocialAccount:
        async with self.session_factory() as session:
            # Create values dictionary with all fields
            values_dict = {
                "platform_type": entity.platform_type,
                "account_id": entity.account_id,
                "account_username": entity.account_username,
                "created_at": entity.created_at,
                "node_hotkey": entity.node_hotkey,
                "node_netuid": entity.node_netuid,
                "extra_data": entity.extra_data,
            }

            # Define primary key fields to exclude from updates
            primary_key_fields = ["platform_type", "account_id"]

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
                pg_insert(SocialAccountORM)
                .values(values_dict)
                .on_conflict_do_update(
                    constraint="uq_platform_type_account_id", set_=update_dict
                )
            )

            # Execute the statement
            await session.execute(stmt)
            await session.commit()

            # Fetch the inserted/updated record
            result = await session.execute(
                select(SocialAccountORM).where(
                    SocialAccountORM.platform_type == entity.platform_type,
                    SocialAccountORM.account_id == entity.account_id,
                )
            )
            updated_orm_account = result.scalars().first()

            return self._orm_to_domain(updated_orm_account)
