from typing import Optional

import httpx
import structlog

from config import bot_settings

logger = structlog.get_logger(__name__)


class BackendClient:
    def __init__(self):
        self.base_url = bot_settings.backend_url
        self.timeout = 10.0

    async def health_check(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{self.base_url}/health")
                return response.status_code == 200
        except Exception as exc:
            logger.warning("health_check_failed", error=str(exc))
            return False

    async def register_user(
        self,
        telegram_id: int,
        username: Optional[str],
        first_name: Optional[str],
        referrer_telegram_id: Optional[int] = None,
    ) -> dict:
        payload = {
            "telegram_id": telegram_id,
            "username": username,
            "first_name": first_name,
            "referrer_telegram_id": referrer_telegram_id,
        }
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                f"{self.base_url}/api/v1/users/register",
                json=payload,
            )
            response.raise_for_status()
            return response.json()

    async def get_user(self, telegram_id: int) -> Optional[dict]:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(f"{self.base_url}/api/v1/users/{telegram_id}")
            if response.status_code == 404:
                return None
            response.raise_for_status()
            return response.json()

    async def get_profile(self, telegram_id: int) -> Optional[dict]:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(f"{self.base_url}/api/v1/profiles/{telegram_id}")
            if response.status_code == 404:
                return None
            response.raise_for_status()
            return response.json()

    async def create_profile(self, data: dict) -> dict:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                f"{self.base_url}/api/v1/profiles",
                json=data,
            )
            response.raise_for_status()
            return response.json()

    async def update_profile(self, telegram_id: int, data: dict) -> dict:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.put(
                f"{self.base_url}/api/v1/profiles/{telegram_id}",
                json=data,
            )
            response.raise_for_status()
            return response.json()

    async def upload_photo(self, telegram_id: int, photo_bytes: bytes, filename: str = "photo.jpg") -> dict:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{self.base_url}/api/v1/profiles/{telegram_id}/photos",
                files={"photo": (filename, photo_bytes, "image/jpeg")},
            )
            response.raise_for_status()
            return response.json()

    async def get_next_profile(self, telegram_id: int) -> Optional[dict]:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(f"{self.base_url}/api/v1/browse/{telegram_id}")
            if response.status_code == 404:
                return None
            response.raise_for_status()
            return response.json()


backend_client = BackendClient()
