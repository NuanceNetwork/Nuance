# database/repositories/node.py
from typing import Optional

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert

from nuance.database.schema import Node as NodeORM
from nuance.database.repositories.base import BaseRepository
from nuance.models import Node


class NodeRepository(BaseRepository[NodeORM, Node]):
    def __init__(self, session_factory):
        super().__init__(NodeORM, session_factory)

    @classmethod
    def _orm_to_domain(cls, orm_obj: NodeORM) -> Node:
        return Node(
            node_hotkey=orm_obj.node_hotkey,
            node_netuid=orm_obj.node_netuid,
        )

    @classmethod
    def _domain_to_orm(cls, domain_obj: Node) -> NodeORM:
        return NodeORM(
            node_hotkey=domain_obj.node_hotkey,
            node_netuid=domain_obj.node_netuid,
        )

    async def get_by_hotkey_netuid(self, hotkey: str, netuid: int) -> Optional[Node]:
        async with self.session_factory() as session:
            result = await session.execute(
                sa.select(NodeORM).where(
                    NodeORM.node_hotkey == hotkey, NodeORM.node_netuid == netuid
                )
            )
            orm_node = result.scalars().first()
            return self._orm_to_domain(orm_node) if orm_node else None

    async def update(self, entity: Node) -> Node:
        async with self.session_factory() as session:
            orm_node = await session.get(
                NodeORM, (entity.node_hotkey, entity.node_netuid)
            )
            if orm_node:
                await session.commit()
                await session.refresh(orm_node)
                return self._orm_to_domain(orm_node)
            return None

    async def upsert(self, entity: Node) -> Node:
        async with self.session_factory() as session:
            # All fields are in primary key so no update
            stmt = (
                pg_insert(NodeORM)
                .values(
                    node_hotkey=entity.node_hotkey,
                    node_netuid=entity.node_netuid,
                )
                .on_conflict_do_nothing(constraint="uq_node_hotkey_node_netuid")
            )

            # Execute the statement
            await session.execute(stmt)
            await session.commit()

            # Fetch the inserted/updated record
            result = await session.execute(
                sa.select(NodeORM).where(
                    NodeORM.node_hotkey == entity.node_hotkey,
                    NodeORM.node_netuid == entity.node_netuid,
                )
            )
            updated_orm_node = result.scalars().first()

            return self._orm_to_domain(updated_orm_node)
