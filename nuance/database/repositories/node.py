# database/repositories/node.py
from typing import Optional

import sqlalchemy as sa

from nuance.database.schema import Node as NodeORM
from nuance.database.repositories.base import BaseRepository
from nuance.models import Node

class NodeRepository(BaseRepository[NodeORM, Node]):
    def __init__(self, session_factory):
        super().__init__(NodeORM, session_factory)
    
    def _to_domain(self, orm_obj: NodeORM) -> Node:
        return Node(
            hotkey=orm_obj.hotkey,
            netuid=orm_obj.netuid,
            node_type=orm_obj.node_type,
            metadata=orm_obj.metadata,
            created_at=orm_obj.created_at,
            updated_at=orm_obj.updated_at
        )
    
    def _to_orm(self, domain_obj: Node) -> NodeORM:
        return NodeORM(
            hotkey=domain_obj.hotkey,
            netuid=domain_obj.netuid,
            node_type=domain_obj.node_type,
            metadata=domain_obj.metadata
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
            return self._to_domain(orm_node) if orm_node else None
    
    async def update(self, entity: Node) -> Node:
        async with self.session_factory() as session:
            orm_node = await session.get(
                NodeORM, (entity.hotkey, entity.netuid)
            )
            if orm_node:
                orm_node.metadata = entity.metadata
                orm_node.node_type = entity.node_type
                await session.commit()
                await session.refresh(orm_node)
                return self._to_domain(orm_node)
            return None