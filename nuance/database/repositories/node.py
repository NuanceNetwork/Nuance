# database/repositories/node.py
from typing import Optional

import sqlalchemy as sa

from nuance.database.schema import Node as NodeORM
from nuance.database.repositories.base import BaseRepository
from nuance.models import Node

class NodeRepository(BaseRepository[NodeORM, Node]):
    def __init__(self, session_factory):
        super().__init__(NodeORM, session_factory)
    
    @classmethod
    def _orm_to_domain(cls, orm_obj: NodeORM) -> Node:
        return Node(
            hotkey=orm_obj.hotkey,
            netuid=orm_obj.netuid,
        )
    
    @classmethod
    def _domain_to_orm(cls, domain_obj: Node) -> NodeORM:
        return NodeORM(
            hotkey=domain_obj.hotkey,
            netuid=domain_obj.netuid,
        )
    
    async def get_by_hotkey_netuid(self, hotkey: str, netuid: int) -> Optional[Node]:
        async with self.session_factory() as session:
            result = await session.execute(
                sa.select(NodeORM).where(
                    NodeORM.hotkey == hotkey, 
                    NodeORM.netuid == netuid
                )
            )
            orm_node = result.scalars().first()
            return self._orm_to_domain(orm_node) if orm_node else None
    
    async def update(self, entity: Node) -> Node:
        async with self.session_factory() as session:
            orm_node = await session.get(
                NodeORM, (entity.hotkey, entity.netuid)
            )
            if orm_node:
                orm_node.metadata = entity.metadata
                await session.commit()
                await session.refresh(orm_node)
                return self._orm_to_domain(orm_node)
            return None