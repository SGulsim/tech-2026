import asyncio
import structlog
import logging

from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.storage.memory import MemoryStorage

from config import bot_settings
from handlers import router
from api_client import backend_client

# Настройка structlog для бота
logging.basicConfig(level=logging.INFO)
structlog.configure(
    processors=[
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.dev.ConsoleRenderer(),
    ],
    wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
    logger_factory=structlog.stdlib.LoggerFactory(),
)
logger = structlog.get_logger(__name__)


async def main() -> None:
    # Инициализируем бота с HTML parse_mode по умолчанию
    bot = Bot(
        token=bot_settings.telegram_bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )

    # MemoryStorage для FSM (в prod заменить на RedisStorage)
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)

    # Проверяем доступность backend перед стартом
    logger.info("checking_backend_connection", url=bot_settings.backend_url)
    is_healthy = await backend_client.health_check()
    if not is_healthy:
        logger.warning("backend_not_available", url=bot_settings.backend_url)
    else:
        logger.info("backend_connected")

    # Удаляем вебхук если был установлен, начинаем polling
    await bot.delete_webhook(drop_pending_updates=True)

    bot_info = await bot.get_me()
    logger.info("bot_started", username=bot_info.username, id=bot_info.id)

    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()
        logger.info("bot_stopped")


if __name__ == "__main__":
    asyncio.run(main())
