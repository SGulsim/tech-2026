import asyncio
import io

import structlog
from minio import Minio
from minio.error import S3Error

from core.config import settings

logger = structlog.get_logger(__name__)

_client: Minio | None = None


def _get_client() -> Minio:
    global _client
    if _client is None:
        _client = Minio(
            settings.minio_endpoint,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            secure=False,
        )
    return _client


async def init_minio() -> None:
    def _setup() -> None:
        client = _get_client()
        if not client.bucket_exists(settings.minio_bucket):
            client.make_bucket(settings.minio_bucket)
            logger.info("minio_bucket_created", bucket=settings.minio_bucket)
        else:
            logger.info("minio_bucket_exists", bucket=settings.minio_bucket)

    await asyncio.to_thread(_setup)


async def upload_photo(key: str, data: bytes, content_type: str = "image/jpeg") -> str:
    def _upload() -> str:
        client = _get_client()
        client.put_object(
            settings.minio_bucket,
            key,
            io.BytesIO(data),
            length=len(data),
            content_type=content_type,
        )
        return f"http://{settings.minio_endpoint}/{settings.minio_bucket}/{key}"

    return await asyncio.to_thread(_upload)


async def delete_photo(key: str) -> None:
    def _delete() -> None:
        _get_client().remove_object(settings.minio_bucket, key)

    await asyncio.to_thread(_delete)
