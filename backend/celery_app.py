import asyncio
import os
import sys

import structlog
from celery import Celery
from celery.schedules import crontab

# Гарантируем, что /app есть в sys.path при любом способе запуска воркера
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

logger = structlog.get_logger(__name__)

_REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
_DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://dating_user:dating_pass@postgres:5432/dating_db",
)

celery_app = Celery(
    "dating_bot",
    broker=_REDIS_URL,
    backend=_REDIS_URL,
)

celery_app.conf.update(
    timezone="UTC",
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    beat_schedule={
        "recalculate-all-ratings-hourly": {
            "task": "celery_app.recalculate_all_ratings",
            "schedule": crontab(minute=0),
        },
    },
)


@celery_app.task(name="celery_app.recalculate_all_ratings", bind=True, max_retries=3)
def recalculate_all_ratings(self):
    try:
        asyncio.run(_async_recalculate(_DATABASE_URL))
    except Exception as exc:
        raise self.retry(exc=exc, countdown=60)


async def _async_recalculate(database_url: str) -> None:
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from models.profile import Profile
    from services.rating_service import RatingService

    engine = create_async_engine(database_url, echo=False)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    try:
        async with session_factory() as session:
            result = await session.execute(select(Profile.id))
            profile_ids = [row[0] for row in result.all()]

            svc = RatingService(session)
            updated = errors = 0

            for profile_id in profile_ids:
                try:
                    await svc.calculate_and_save(profile_id)
                    updated += 1
                except Exception as exc:
                    errors += 1
                    logger.error("rating_recalc_error", profile_id=profile_id, error=str(exc))

            await session.commit()
            logger.info("ratings_batch_recalculated", updated=updated, errors=errors)
    finally:
        await engine.dispose()
