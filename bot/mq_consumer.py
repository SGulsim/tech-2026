import json

import aio_pika
import structlog

from config import bot_settings

logger = structlog.get_logger(__name__)

QUEUE_NOTIFICATIONS = "bot.notifications"

_connection: aio_pika.RobustConnection | None = None


async def start_notification_consumer(bot) -> None:
    global _connection
    _connection = await aio_pika.connect_robust(bot_settings.rabbitmq_url)
    channel = await _connection.channel()
    queue = await channel.declare_queue(QUEUE_NOTIFICATIONS, durable=True)

    async def on_message(message: aio_pika.IncomingMessage) -> None:
        async with message.process():
            try:
                payload = json.loads(message.body)
                event_type = payload.get("type")
                if event_type == "match":
                    await _handle_match(bot, payload)
            except Exception as exc:
                logger.error("notification_processing_error", error=str(exc))

    await queue.consume(on_message)
    logger.info("notification_consumer_started")


async def _handle_match(bot, payload: dict) -> None:
    user1_id = payload.get("user1_telegram_id")
    user2_id = payload.get("user2_telegram_id")
    user1_name = payload.get("user1_name", "Аноним")
    user2_name = payload.get("user2_name", "Аноним")

    text_for_user1 = (
        f"🎉 <b>Мэтч!</b>\n\n"
        f"Вам понравились друг другу с <b>{user2_name}</b>!\n"
        "Можно начинать общаться 💬"
    )
    text_for_user2 = (
        f"🎉 <b>Мэтч!</b>\n\n"
        f"Вам понравились друг другу с <b>{user1_name}</b>!\n"
        "Можно начинать общаться 💬"
    )

    if user1_id:
        try:
            await bot.send_message(user1_id, text_for_user1, parse_mode="HTML")
        except Exception as exc:
            logger.warning("match_notify_failed", user=user1_id, error=str(exc))

    if user2_id:
        try:
            await bot.send_message(user2_id, text_for_user2, parse_mode="HTML")
        except Exception as exc:
            logger.warning("match_notify_failed", user=user2_id, error=str(exc))

    logger.info("match_notified", user1=user1_id, user2=user2_id)
