from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from core.config import settings

_is_postgres = settings.database_url.startswith("postgresql")
engine = create_async_engine(
    settings.database_url,
    echo=False,
    # SQLite (используется в тестах) не поддерживает pool_size/max_overflow
    **({
        "pool_size": 10,
        "max_overflow": 20,
        "pool_pre_ping": True,
    } if _is_postgres else {}),
)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def init_db() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
