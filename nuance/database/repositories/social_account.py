# database/repositories/social_account.py
from typing import Optional, List
from sqlalchemy import select

from nuance.database.schema import Node as NodeORM
from nuance.database.schema import SocialAccount as SocialAccountORM
from nuance.models import SocialAccount
from nuance.database.repositories.base import BaseRepository

class SocialAccountRepository(BaseRepository[SocialAccountORM, SocialAccount]):
    def __init__(self, session_factory):
        super().__init__(SocialAccountORM, session_factory)
    
    def _to_domain(self, orm_obj: SocialAccountORM) -> SocialAccount:
        return SocialAccount(
            id=orm_obj.id,
            platform_type=orm_obj.platform_type,
            account_id=orm_obj.account_id,
            username=orm_obj.username,
            node_hotkey=orm_obj.node.hotkey,
            node_netuid=orm_obj.node.netuid,
            extra_data=orm_obj.extra_data,
            created_at=orm_obj.created_at,
            updated_at=orm_obj.updated_at
        )
    
    def _to_orm(self, domain_obj: SocialAccount) -> SocialAccountORM:
        return SocialAccountORM(
            id=domain_obj.id,
            platform_type=domain_obj.platform_type,
            account_id=domain_obj.account_id,
            username=domain_obj.username,
            node_id=domain_obj.node_id,
            extra_data=domain_obj.extra_data
        )
    
    async def get_by_platform_and_account_id(
        self, platform_type: str, account_id: str
    ) -> Optional[SocialAccount]:
        async with self.session_factory() as session:
            result = await session.execute(
                select(SocialAccountORM).where(
                    SocialAccountORM.platform_type == platform_type,
                    SocialAccountORM.account_id == account_id
                )
            )
            orm_account = result.scalars().first()
            return self._to_domain(orm_account) if orm_account else None
    
    async def get_by_node(
        self, node_hotkey: str, node_netuid: int
    ) -> List[SocialAccount]:
        async with self.session_factory() as session:
            result = await session.execute(
                select(SocialAccountORM).join(SocialAccountORM.node).where(
                    NodeORM.hotkey == node_hotkey,
                    NodeORM.netuid == node_netuid
                )
            )
            return [self._to_domain(obj) for obj in result.scalars().all()]