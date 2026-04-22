import asyncio
import logging

import structlog
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from api_client import backend_client
from config import bot_settings
from handlers import router
from mq_client import close_mq, init_mq
from mq_consumer import start_notification_consumer

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
    bot = Bot(
        token=bot_settings.telegram_bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )

    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)

    logger.info("checking_backend", url=bot_settings.backend_url)
    if not await backend_client.health_check():
        logger.warning("backend_not_available")
    else:
        logger.info("backend_connected")

    # Инициализируем RabbitMQ
    try:
        await init_mq()
        # Запускаем потребитель уведомлений о мэтчах в фоне
        asyncio.create_task(start_notification_consumer(bot))
        logger.info("rabbitmq_ready")
    except Exception as exc:
        logger.warning("rabbitmq_not_available", error=str(exc))

    await bot.delete_webhook(drop_pending_updates=True)
    bot_info = await bot.get_me()
    logger.info("bot_started", username=bot_info.username)

    try:
        await dp.start_polling(bot)
    finally:
        await close_mq()
        await bot.session.close()
        logger.info("bot_stopped")


if __name__ == "__main__":
    asyncio.run(main())
