"""
Тесты Dating Bot — Этап 2

Покрытие:
  - UserService: регистрация (новый, повторный, реферал, несуществующий реферал)
  - API endpoints: /health, /register, /users/{id}
  - Валидация Pydantic (422 при отсутствии обязательных полей)
  - Клавиатуры бота (тип, кнопки, callback_data)
  - BackendClient (health_check, register_user — через mock)
"""

import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

# ── Env vars ПЕРЕД импортами (pydantic-settings читает при создании Settings) ──
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test_token_123")
os.environ.setdefault("BACKEND_URL", "http://localhost:8000")

# ── Пути к модулям ──────────────────────────────────────────────────────────
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend"))  # index 0 — импорты backend в приоритете
sys.path.insert(1, os.path.join(ROOT, "bot"))       # index 1 — bot-модули когда нет в backend

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.pool import StaticPool

from db.session import Base, get_db
from services.user_service import UserService
from schemas.user import UserCreate
from main import app  # backend/main.py

from keyboards import main_menu_keyboard, welcome_keyboard, profile_actions_keyboard
from aiogram.types import ReplyKeyboardMarkup, InlineKeyboardMarkup


# ════════════════════════════════════════════════════════════
# FIXTURES
# ════════════════════════════════════════════════════════════

def _make_engine():
    """SQLite in-memory с единственным соединением (StaticPool)."""
    return create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )


@pytest_asyncio.fixture
async def db():
    """Чистая БД на каждый тест."""
    engine = _make_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield session

    await engine.dispose()


@pytest_asyncio.fixture
async def api(db):
    """
    FastAPI TestClient с подменой get_db → тестовая SQLite-сессия.
    init_db() из lifespan заглушен, чтобы не трогать реальный Postgres.
    """
    async def override_get_db():
        try:
            yield db
            await db.commit()
        except Exception:
            await db.rollback()
            raise

    app.dependency_overrides[get_db] = override_get_db

    with patch("main.init_db", new=AsyncMock()):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            yield client

    app.dependency_overrides.clear()


# ════════════════════════════════════════════════════════════
# USERSERVICE — юнит-тесты
# ════════════════════════════════════════════════════════════

class TestUserService:

    async def test_register_new_user(self, db):
        """Новый пользователь: is_new=True, данные сохраняются."""
        service = UserService(db)
        result = await service.register(
            UserCreate(telegram_id=1001, username="anna", first_name="Анна")
        )

        assert result.is_new is True
        assert result.telegram_id == 1001
        assert result.username == "anna"
        assert result.first_name == "Анна"
        assert result.referrer_id is None

    async def test_register_idempotency(self, db):
        """Повторный /start одного пользователя: is_new=False, id не меняется."""
        service = UserService(db)
        data = UserCreate(telegram_id=1002, first_name="Борис")

        first = await service.register(data)
        await db.commit()
        second = await service.register(data)

        assert second.is_new is False
        assert first.id == second.id

    async def test_register_with_valid_referral(self, db):
        """Реферал: referrer_id сохраняется как внутренний id, не telegram_id."""
        service = UserService(db)

        referrer = await service.register(UserCreate(telegram_id=9001, first_name="Реферер"))
        await db.commit()

        new_user = await service.register(
            UserCreate(telegram_id=1003, first_name="Новый", referrer_telegram_id=9001)
        )

        assert new_user.is_new is True
        assert new_user.referrer_id == referrer.id  # внутренний id, не telegram_id

    async def test_register_with_nonexistent_referral(self, db):
        """Несуществующий реферер: пользователь создаётся, referrer_id=None."""
        service = UserService(db)
        result = await service.register(
            UserCreate(telegram_id=1004, first_name="Тест", referrer_telegram_id=99999)
        )

        assert result.is_new is True
        assert result.referrer_id is None

    async def test_get_by_telegram_id_found(self, db):
        """Поиск существующего пользователя."""
        service = UserService(db)
        await service.register(UserCreate(telegram_id=1005, first_name="Найди меня"))
        await db.commit()

        user = await service.get_by_telegram_id(1005)
        assert user is not None
        assert user.telegram_id == 1005

    async def test_get_by_telegram_id_not_found(self, db):
        """Поиск несуществующего пользователя возвращает None."""
        service = UserService(db)
        user = await service.get_by_telegram_id(99999)
        assert user is None

    async def test_username_can_be_none(self, db):
        """username необязателен — Telegram не требует его."""
        service = UserService(db)
        result = await service.register(UserCreate(telegram_id=1006, username=None))
        assert result.username is None


# ════════════════════════════════════════════════════════════
# API ENDPOINTS — интеграционные тесты
# ════════════════════════════════════════════════════════════

class TestHealthEndpoint:

    async def test_health_returns_ok(self, api):
        r = await api.get("/health")
        assert r.status_code == 200
        assert r.json() == {"status": "ok"}


class TestRegisterEndpoint:

    async def test_register_new_user(self, api):
        r = await api.post("/api/v1/users/register", json={
            "telegram_id": 2001,
            "username": "testuser",
            "first_name": "Тест",
        })
        assert r.status_code == 200
        data = r.json()
        assert data["telegram_id"] == 2001
        assert data["is_new"] is True
        assert data["username"] == "testuser"

    async def test_register_idempotent(self, api):
        """Два запроса с одним telegram_id: второй is_new=False, id одинаковый."""
        payload = {"telegram_id": 2002, "first_name": "Идемпотент"}

        r1 = await api.post("/api/v1/users/register", json=payload)
        r2 = await api.post("/api/v1/users/register", json=payload)

        assert r1.status_code == 200
        assert r2.status_code == 200
        assert r1.json()["id"] == r2.json()["id"]
        assert r1.json()["is_new"] is True
        assert r2.json()["is_new"] is False

    async def test_register_with_referral(self, api):
        """Регистрация с реферальным параметром."""
        await api.post("/api/v1/users/register", json={
            "telegram_id": 9002,
            "first_name": "Реферер",
        })
        r = await api.post("/api/v1/users/register", json={
            "telegram_id": 2003,
            "first_name": "Новый",
            "referrer_telegram_id": 9002,
        })
        assert r.status_code == 200
        assert r.json()["referrer_id"] is not None

    async def test_register_missing_telegram_id(self, api):
        """Без telegram_id — Pydantic вернёт 422."""
        r = await api.post("/api/v1/users/register", json={"username": "notelegrамid"})
        assert r.status_code == 422

    async def test_register_wrong_type(self, api):
        """telegram_id строкой вместо int — 422."""
        r = await api.post("/api/v1/users/register", json={
            "telegram_id": "not_a_number",
        })
        assert r.status_code == 422


class TestGetUserEndpoint:

    async def test_get_existing_user(self, api):
        await api.post("/api/v1/users/register", json={
            "telegram_id": 3001,
            "first_name": "Поиск",
        })
        r = await api.get("/api/v1/users/3001")
        assert r.status_code == 200
        assert r.json()["telegram_id"] == 3001

    async def test_get_nonexistent_user(self, api):
        r = await api.get("/api/v1/users/99999999")
        assert r.status_code == 404

    async def test_get_user_returns_correct_fields(self, api):
        """Ответ содержит все ожидаемые поля."""
        await api.post("/api/v1/users/register", json={
            "telegram_id": 3002,
            "username": "fields_test",
            "first_name": "Поля",
        })
        r = await api.get("/api/v1/users/3002")
        data = r.json()

        for field in ("id", "telegram_id", "username", "first_name", "referrer_id", "created_at"):
            assert field in data, f"Поле '{field}' отсутствует в ответе"


# ════════════════════════════════════════════════════════════
# КЛАВИАТУРЫ — юнит-тесты
# ════════════════════════════════════════════════════════════

class TestKeyboards:

    def test_main_menu_keyboard_type(self):
        kb = main_menu_keyboard()
        assert isinstance(kb, ReplyKeyboardMarkup)

    def test_main_menu_keyboard_buttons(self):
        kb = main_menu_keyboard()
        texts = {btn.text for row in kb.keyboard for btn in row}
        assert "👤 Моя анкета" in texts
        assert "❤️ Смотреть анкеты" in texts
        assert "👥 Пригласить друга" in texts
        assert "⚙️ Настройки" in texts

    def test_welcome_keyboard_new_user(self):
        kb = welcome_keyboard(is_new=True)
        assert isinstance(kb, InlineKeyboardMarkup)
        cb_data = {btn.callback_data for row in kb.inline_keyboard for btn in row}
        assert "create_profile" in cb_data
        assert "how_it_works" in cb_data

    def test_welcome_keyboard_returning_user(self):
        kb = welcome_keyboard(is_new=False)
        assert isinstance(kb, InlineKeyboardMarkup)
        cb_data = {btn.callback_data for row in kb.inline_keyboard for btn in row}
        assert "my_profile" in cb_data
        assert "browse_profiles" in cb_data

    def test_welcome_keyboard_new_vs_returning_differ(self):
        """Клавиатуры для нового и вернувшегося пользователя — разные."""
        new_cb = {btn.callback_data
                  for row in welcome_keyboard(is_new=True).inline_keyboard
                  for btn in row}
        ret_cb = {btn.callback_data
                  for row in welcome_keyboard(is_new=False).inline_keyboard
                  for btn in row}
        assert new_cb != ret_cb

    def test_profile_actions_keyboard(self):
        kb = profile_actions_keyboard()
        assert isinstance(kb, InlineKeyboardMarkup)
        cb_data = {btn.callback_data for row in kb.inline_keyboard for btn in row}
        assert "back_to_menu" in cb_data


# ════════════════════════════════════════════════════════════
# BACKENDCLIENT — тесты с mock httpx
# ════════════════════════════════════════════════════════════

class TestBackendClient:

    def _make_mock_http_client(self, method: str, return_value):
        """Вспомогательный метод: создаёт mock для httpx.AsyncClient."""
        mock_instance = AsyncMock()
        setattr(mock_instance, method, AsyncMock(return_value=return_value))
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        return mock_instance

    async def test_health_check_success(self):
        from api_client import BackendClient
        client = BackendClient()

        mock_response = MagicMock(status_code=200)
        mock_http = self._make_mock_http_client("get", mock_response)

        with patch("httpx.AsyncClient", return_value=mock_http):
            result = await client.health_check()

        assert result is True

    async def test_health_check_connection_error(self):
        from api_client import BackendClient
        client = BackendClient()

        mock_instance = AsyncMock()
        mock_instance.get = AsyncMock(side_effect=Exception("Connection refused"))
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)

        with patch("httpx.AsyncClient", return_value=mock_instance):
            result = await client.health_check()

        assert result is False

    async def test_health_check_non_200(self):
        """Backend вернул не 200 — health_check должен вернуть False."""
        from api_client import BackendClient
        client = BackendClient()

        mock_response = MagicMock(status_code=503)
        mock_http = self._make_mock_http_client("get", mock_response)

        with patch("httpx.AsyncClient", return_value=mock_http):
            result = await client.health_check()

        assert result is False

    async def test_register_user_success(self):
        from api_client import BackendClient
        client = BackendClient()

        mock_response = MagicMock()
        mock_response.json.return_value = {"id": 42, "telegram_id": 111, "is_new": True}
        mock_response.raise_for_status = MagicMock()
        mock_http = self._make_mock_http_client("post", mock_response)

        with patch("httpx.AsyncClient", return_value=mock_http):
            result = await client.register_user(
                telegram_id=111,
                username="anna",
                first_name="Анна",
            )

        assert result["is_new"] is True
        assert result["telegram_id"] == 111
        assert result["id"] == 42

    async def test_register_user_sends_correct_payload(self):
        """Проверяем что клиент отправляет правильный JSON."""
        from api_client import BackendClient
        client = BackendClient()

        mock_response = MagicMock()
        mock_response.json.return_value = {"id": 1, "telegram_id": 222, "is_new": True}
        mock_response.raise_for_status = MagicMock()

        mock_post = AsyncMock(return_value=mock_response)
        mock_instance = AsyncMock()
        mock_instance.post = mock_post
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)

        with patch("httpx.AsyncClient", return_value=mock_instance):
            await client.register_user(
                telegram_id=222,
                username="boris",
                first_name="Борис",
                referrer_telegram_id=999,
            )

        call_kwargs = mock_post.call_args
        sent_json = call_kwargs.kwargs.get("json") or call_kwargs.args[1]
        assert sent_json["telegram_id"] == 222
        assert sent_json["referrer_telegram_id"] == 999

    async def test_get_user_found(self):
        from api_client import BackendClient
        client = BackendClient()

        mock_response = MagicMock(status_code=200)
        mock_response.json.return_value = {"id": 1, "telegram_id": 333}
        mock_response.raise_for_status = MagicMock()
        mock_http = self._make_mock_http_client("get", mock_response)

        with patch("httpx.AsyncClient", return_value=mock_http):
            result = await client.get_user(333)

        assert result is not None
        assert result["telegram_id"] == 333

    async def test_get_user_not_found(self):
        from api_client import BackendClient
        client = BackendClient()

        mock_response = MagicMock(status_code=404)
        mock_http = self._make_mock_http_client("get", mock_response)

        with patch("httpx.AsyncClient", return_value=mock_http):
            result = await client.get_user(99999)

        assert result is None
