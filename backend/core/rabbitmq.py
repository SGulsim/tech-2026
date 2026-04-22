import json
from typing import Callable, Awaitable

import aio_pika
import structlog

from core.config import settings

logger = structlog.get_logger(__name__)

QUEUE_ACTIONS = "profile.actions"
QUEUE_NOTIFICATIONS = "bot.notifications"

_connection: aio_pika.RobustConnection | None = None
_channel: aio_pika.Channel | None = None


async def init_rabbitmq() -> None:
    global _connection, _channel
    _connection = await aio_pika.connect_robust(settings.rabbitmq_url)
    _channel = await _connection.channel()
    await _channel.declare_queue(QUEUE_ACTIONS, durable=True)
    await _channel.declare_queue(QUEUE_NOTIFICATIONS, durable=True)
    logger.info("rabbitmq_initialized")


async def close_rabbitmq() -> None:
    if _connection:
        await _connection.close()


async def publish(queue_name: str, payload: dict) -> None:
    await _channel.default_exchange.publish(
        aio_pika.Message(
            body=json.dumps(payload, ensure_ascii=False).encode(),
            delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
        ),
        routing_key=queue_name,
    )


async def consume(queue_name: str, callback: Callable[[dict], Awaitable[None]]) -> None:
    queue = await _channel.declare_queue(queue_name, durable=True)

    async def on_message(message: aio_pika.IncomingMessage) -> None:
        async with message.process():
            try:
                payload = json.loads(message.body)
                await callback(payload)
            except Exception as exc:
                logger.error("mq_processing_error", queue=queue_name, error=str(exc))

    await queue.consume(on_message)
    logger.info("mq_consumer_started", queue=queue_name)
