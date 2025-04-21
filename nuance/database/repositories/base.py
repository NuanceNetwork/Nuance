# database/repositories/base.py
from typing import TypeVar, Generic, Optional, Type, Callable, AsyncContextManager

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from nuance.database.schema import Base

T = TypeVar('T', bound=Base)
M = TypeVar('M')  # Domain model type

class BaseRepository(Generic[T, M]):
    """Base repository with common CRUD operations."""
    
    def __init__(self, model_cls: Type[T], session_factory):
        self.model_cls: Type[T] = model_cls
        self.session_factory: Callable[[], AsyncContextManager[AsyncSession]] = session_factory
    
    # Convert between ORM and domain models
    def _orm_to_domain(self, orm_obj: T) -> M:
        raise NotImplementedError("Subclasses must implement _orm_to_domain")
    
    def _domain_to_orm(self, domain_obj: M) -> T:
        raise NotImplementedError("Subclasses must implement _domain_to_orm")
    
    async def get_by_id(self, id) -> Optional[M]:
        async with self.session_factory() as session:
            result = await session.get(self.model_cls, id)
            return self._orm_to_domain(result) if result else None
    
    async def get_all(self) -> list[M]:
        async with self.session_factory() as session:
            result = await session.execute(sa.select(self.model_cls))
            return [self._orm_to_domain(obj) for obj in result.scalars().all()]
    
    async def create(self, entity: M) -> M:
        orm_obj = self._domain_to_orm(entity)
        
        async with self.session_factory() as session:
            session.add(orm_obj)
            await session.commit()
            await session.refresh(orm_obj)
            
            return self._orm_to_domain(orm_obj)
    
    async def update(self, entity: M) -> M:
        # Implementation depends on how you identify entities
        raise NotImplementedError("Subclasses must implement update")
    
    async def delete(self, id) -> bool:
        async with self.session_factory() as session:
            obj = await session.get(self.model_cls, id)
            if obj:
                await session.delete(obj)
                await session.commit()
                return True
            return False