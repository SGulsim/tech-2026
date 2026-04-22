import json

import aio_pika
import structlog

from config import bot_settings

logger = structlog.get_logger(__name__)

QUEUE_ACTIONS = "profile.actions"

_connection: aio_pika.RobustConnection | None = None
_channel: aio_pika.Channel | None = None


async def init_mq() -> None:
    global _connection, _channel
    _connection = await aio_pika.connect_robust(bot_settings.rabbitmq_url)
    _channel = await _connection.channel()
    await _channel.declare_queue(QUEUE_ACTIONS, durable=True)
    logger.info("bot_mq_publisher_ready")


async def close_mq() -> None:
    if _connection:
        await _connection.close()


async def publish_action(from_telegram_id: int, to_profile_id: int, action: str) -> None:
    payload = {
        "action": action,
        "from_telegram_id": from_telegram_id,
        "to_profile_id": to_profile_id,
    }
    await _channel.default_exchange.publish(
        aio_pika.Message(
            body=json.dumps(payload).encode(),
            delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
        ),
        routing_key=QUEUE_ACTIONS,
    )
    logger.info("action_published", action=action, from_id=from_telegram_id, to_profile=to_profile_id)
