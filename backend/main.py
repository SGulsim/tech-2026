import time
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

import models  # noqa: F401 — регистрируем все модели до init_db
from api.routes.browse import router as browse_router
from api.routes.profiles import router as profiles_router
from api.routes.users import router as users_router
from core.logging import setup_logging
from core.minio_client import init_minio
from core.rabbitmq import QUEUE_ACTIONS, consume, init_rabbitmq, close_rabbitmq
from core.redis_client import close_redis, init_redis
from db.session import init_db

setup_logging()
logger = structlog.get_logger(__name__)


async def _handle_action_event(payload: dict) -> None:
    from db.session import AsyncSessionLocal
    from services.like_service import LikeService

    action = payload.get("action")
    from_telegram_id = payload.get("from_telegram_id")
    to_profile_id = payload.get("to_profile_id")

    if not all([action, from_telegram_id, to_profile_id]):
        logger.warning("invalid_action_event", payload=payload)
        return

    async with AsyncSessionLocal() as session:
        try:
            svc = LikeService(session)
            await svc.process_action(
                from_telegram_id=from_telegram_id,
                to_profile_id=to_profile_id,
                is_skip=(action == "skip"),
            )
            await session.commit()
        except Exception as exc:
            await session.rollback()
            logger.error("action_event_error", error=str(exc), payload=payload)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("starting_up")
    await init_db()
    logger.info("database_initialized")

    await init_redis()
    await init_rabbitmq()

    try:
        await init_minio()
    except Exception as exc:
        logger.warning("minio_init_failed", error=str(exc))

    # Запускаем потребитель событий лайков/скипов от бота
    await consume(QUEUE_ACTIONS, _handle_action_event)

    logger.info("all_services_initialized")
    yield

    await close_redis()
    await close_rabbitmq()
    logger.info("shutting_down")


app = FastAPI(
    title="Dating Bot API",
    description="Backend для Telegram-бота знакомств",
    version="0.2.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(users_router)
app.include_router(profiles_router)
app.include_router(browse_router)


@app.get("/health", tags=["health"])
async def health():
    return {"status": "ok"}


@app.middleware("http")
async def logging_middleware(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    duration_ms = (time.perf_counter() - start) * 1000
    logger.info(
        "http_request",
        method=request.method,
        path=request.url.path,
        status_code=response.status_code,
        duration_ms=round(duration_ms, 2),
    )
    return response
