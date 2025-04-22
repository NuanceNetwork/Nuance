#nuance/database/engine.py
import contextlib
from typing import Any, AsyncIterator

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, AsyncConnection
from sqlalchemy.ext.asyncio import async_sessionmaker

from nuance.database.schema import Base
from nuance.settings import settings


class DatabaseSessionManager:
    """
    Singleton manager for database sessions using PostgreSQL.
    Handles async session creation and connection management.
    """
    _instance = None
    
    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self, db_url: str, engine_kwargs: dict[str, Any] = None):
        if self._initialized:
            return
            
        self._engine = create_async_engine(
            db_url, 
            **(engine_kwargs or {"echo": settings.debug})
        )
        self._sessionmaker = async_sessionmaker(
            autocommit=False, 
            autoflush=False,
            expire_on_commit=False,
            bind=self._engine
        )
        self._initialized = True
    
    async def close(self):
        """Close the database engine."""
        if self._engine is None:
            raise Exception("DatabaseSessionManager is not initialized")
        await self._engine.dispose()
        self._engine = None
        self._sessionmaker = None
        self._initialized = False
    
    @contextlib.asynccontextmanager
    async def connect(self) -> AsyncIterator[AsyncConnection]:
        """Get a database connection."""
        if self._engine is None:
            raise Exception("DatabaseSessionManager is not initialized")
        async with self._engine.begin() as connection:
            try:
                yield connection
            except Exception:
                await connection.rollback()
                raise
    
    @contextlib.asynccontextmanager
    async def session(self) -> AsyncIterator[AsyncSession]:
        """Get a database session."""
        if self._sessionmaker is None:
            raise Exception("DatabaseSessionManager is not initialized")
        session = self._sessionmaker()
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
    
    async def create_all(self):
        """Create all tables defined in models."""
        async with self.connect() as conn:
            await conn.run_sync(Base.metadata.create_all)
    
    async def drop_all(self):
        """Drop all tables defined in models."""
        async with self.connect() as conn:
            await conn.run_sync(Base.metadata.drop_all)


# Create global session manager instance
sessionmanager = DatabaseSessionManager(settings.database_url, settings.database_engine_kwargs)

@contextlib.asynccontextmanager
async def get_db_session() -> AsyncIterator[AsyncSession]:
    """Get a database session for dependency injection."""
    async with sessionmanager.session() as session:
        yield session
        
if __name__ == "__main__":
    import asyncio
    loop = asyncio.get_event_loop()
    loop.run_until_complete(sessionmanager.drop_all())
    loop.run_until_complete(sessionmanager.create_all())