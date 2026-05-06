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


# ════════════════════════════════════════════════════════════
# RATINGSERVICE — юнит-тесты (этап 3/4)
# ════════════════════════════════════════════════════════════

class TestRatingService:

    async def _create_user_and_profile(self, db, telegram_id: int, **profile_kwargs):
        from services.user_service import UserService
        from services.profile_service import ProfileService
        from schemas.user import UserCreate
        from schemas.profile import ProfileCreate

        user_svc = UserService(db)
        user = await user_svc.register(UserCreate(telegram_id=telegram_id, first_name="Test"))
        await db.flush()

        profile_svc = ProfileService(db)
        defaults = dict(
            telegram_id=telegram_id,
            name="Тест",
            age=25,
            gender="female",
            city="Алматы",
        )
        defaults.update(profile_kwargs)
        profile = await profile_svc.create(ProfileCreate(**defaults))
        await db.flush()
        return user, profile

    async def test_calculate_creates_rating_record(self, db):
        """calculate_and_save создаёт запись Rating для новой анкеты."""
        from sqlalchemy import select
        from services.rating_service import RatingService
        from models.rating import Rating

        _, profile = await self._create_user_and_profile(db, telegram_id=6001)

        svc = RatingService(db)
        rating = await svc.calculate_and_save(profile.id)
        await db.flush()

        result = await db.execute(select(Rating).where(Rating.profile_id == profile.id))
        saved = result.scalar_one_or_none()

        assert saved is not None
        assert saved.final_score == rating.final_score

    async def test_completeness_full_profile(self, db):
        """Анкета со всеми полями (без фото) получает score >= 75."""
        from services.rating_service import RatingService

        _, profile = await self._create_user_and_profile(
            db,
            telegram_id=6002,
            bio="Привет, меня зовут Тест и я люблю кофе!",
            interests="книги, музыка, спорт",
            preferences="ищу мужчину",
        )
        svc = RatingService(db)
        rating = await svc.calculate_and_save(profile.id)

        assert rating.level1_score >= 75.0

    async def test_completeness_minimal_profile(self, db):
        """Анкета с минимальными полями получает score < 75."""
        from services.profile_service import ProfileService
        from services.user_service import UserService
        from services.rating_service import RatingService
        from schemas.user import UserCreate
        from schemas.profile import ProfileCreate

        user_svc = UserService(db)
        user = await user_svc.register(UserCreate(telegram_id=6003, first_name="T"))
        await db.flush()

        profile_svc = ProfileService(db)
        profile = await profile_svc.create(ProfileCreate(
            telegram_id=6003,
            name="T",
            age=20,
            gender="male",
            city="Нур-Султан",
        ))
        await db.flush()

        svc = RatingService(db)
        rating = await svc.calculate_and_save(profile.id)

        assert rating.level1_score < 75.0

    async def test_calculate_update_on_second_call(self, db):
        """Повторный вызов обновляет existing Rating, не создаёт дубль."""
        from sqlalchemy import select, func
        from services.rating_service import RatingService
        from models.rating import Rating

        _, profile = await self._create_user_and_profile(db, telegram_id=6004)

        svc = RatingService(db)
        await svc.calculate_and_save(profile.id)
        await db.flush()
        await svc.calculate_and_save(profile.id)
        await db.flush()

        count_result = await db.execute(
            select(func.count()).where(Rating.profile_id == profile.id)
        )
        assert count_result.scalar() == 1

    async def test_final_score_formula(self, db):
        """final_score = level1*0.35 + level2*0.50 + referral*0.15."""
        from services.rating_service import RatingService

        _, profile = await self._create_user_and_profile(db, telegram_id=6005)

        svc = RatingService(db)
        rating = await svc.calculate_and_save(profile.id)

        expected = rating.level1_score * 0.35 + rating.level2_score * 0.50 + rating.referral_bonus * 0.15
        assert abs(rating.final_score - expected) < 0.001


# ════════════════════════════════════════════════════════════
# LIKESERVICE — юнит-тесты (этап 3/4)
# ════════════════════════════════════════════════════════════

class TestLikeService:

    async def _setup_two_users(self, db):
        """Создаёт двух пользователей с анкетами. Возвращает (user1, profile1, user2, profile2)."""
        from services.user_service import UserService
        from services.profile_service import ProfileService
        from schemas.user import UserCreate
        from schemas.profile import ProfileCreate

        user_svc = UserService(db)
        profile_svc = ProfileService(db)

        u1 = await user_svc.register(UserCreate(telegram_id=7001, first_name="Алия"))
        await db.flush()
        p1 = await profile_svc.create(ProfileCreate(
            telegram_id=7001, name="Алия", age=23, gender="female", city="Алматы"
        ))
        await db.flush()

        u2 = await user_svc.register(UserCreate(telegram_id=7002, first_name="Данияр"))
        await db.flush()
        p2 = await profile_svc.create(ProfileCreate(
            telegram_id=7002, name="Данияр", age=26, gender="male", city="Алматы"
        ))
        await db.flush()

        return u1, p1, u2, p2

    async def test_like_creates_record(self, db):
        """process_action с is_skip=False создаёт запись лайка."""
        from sqlalchemy import select
        from services.like_service import LikeService
        from models.like import Like

        u1, p1, u2, p2 = await self._setup_two_users(db)

        with patch("services.like_service.publish", new=AsyncMock()):
            svc = LikeService(db)
            await svc.process_action(
                from_telegram_id=u1.telegram_id,
                to_profile_id=p2.id,
                is_skip=False,
            )
            await db.flush()

        result = await db.execute(
            select(Like).where(Like.from_user_id == u1.id, Like.to_profile_id == p2.id)
        )
        like = result.scalar_one_or_none()
        assert like is not None
        assert like.is_skip is False

    async def test_skip_creates_record(self, db):
        """process_action с is_skip=True создаёт запись скипа."""
        from sqlalchemy import select
        from services.like_service import LikeService
        from models.like import Like

        u1, p1, u2, p2 = await self._setup_two_users(db)

        with patch("services.like_service.publish", new=AsyncMock()):
            svc = LikeService(db)
            await svc.process_action(
                from_telegram_id=u1.telegram_id,
                to_profile_id=p2.id,
                is_skip=True,
            )
            await db.flush()

        result = await db.execute(
            select(Like).where(Like.from_user_id == u1.id, Like.to_profile_id == p2.id)
        )
        like = result.scalar_one_or_none()
        assert like is not None
        assert like.is_skip is True

    async def test_duplicate_like_ignored(self, db):
        """Второй лайк той же анкеты не создаёт дубль."""
        from sqlalchemy import select, func
        from services.like_service import LikeService
        from models.like import Like

        u1, p1, u2, p2 = await self._setup_two_users(db)

        with patch("services.like_service.publish", new=AsyncMock()):
            svc = LikeService(db)
            await svc.process_action(u1.telegram_id, p2.id, is_skip=False)
            await db.flush()
            await svc.process_action(u1.telegram_id, p2.id, is_skip=False)
            await db.flush()

        count = await db.execute(
            select(func.count()).where(
                Like.from_user_id == u1.id,
                Like.to_profile_id == p2.id,
            )
        )
        assert count.scalar() == 1

    async def test_mutual_like_creates_match(self, db):
        """Взаимный лайк создаёт мэтч и публикует событие в очередь."""
        from sqlalchemy import select
        from services.like_service import LikeService
        from models.match import Match

        u1, p1, u2, p2 = await self._setup_two_users(db)

        mock_publish = AsyncMock()
        with patch("services.like_service.publish", new=mock_publish):
            svc = LikeService(db)
            await svc.process_action(u1.telegram_id, p2.id, is_skip=False)
            await db.flush()
            await svc.process_action(u2.telegram_id, p1.id, is_skip=False)
            await db.flush()

        result = await db.execute(
            select(Match).where(
                ((Match.user1_id == u1.id) & (Match.user2_id == u2.id))
                | ((Match.user1_id == u2.id) & (Match.user2_id == u1.id))
            )
        )
        match = result.scalar_one_or_none()
        assert match is not None
        assert mock_publish.called

    async def test_no_match_on_skip(self, db):
        """Лайк + скип не создаёт мэтч."""
        from sqlalchemy import select
        from services.like_service import LikeService
        from models.match import Match

        u1, p1, u2, p2 = await self._setup_two_users(db)

        with patch("services.like_service.publish", new=AsyncMock()):
            svc = LikeService(db)
            await svc.process_action(u1.telegram_id, p2.id, is_skip=False)
            await db.flush()
            await svc.process_action(u2.telegram_id, p1.id, is_skip=True)
            await db.flush()

        result = await db.execute(select(Match))
        matches = result.scalars().all()
        assert len(matches) == 0

    async def test_unknown_user_returns_none(self, db):
        """Лайк от несуществующего пользователя не падает, возвращает None."""
        from services.like_service import LikeService

        with patch("services.like_service.publish", new=AsyncMock()):
            svc = LikeService(db)
            result = await svc.process_action(
                from_telegram_id=99999,
                to_profile_id=1,
                is_skip=False,
            )

        assert result is None


# ════════════════════════════════════════════════════════════
# CACHESERVICE — юнит-тесты с fakeredis (этап 3/4)
# ════════════════════════════════════════════════════════════

class TestCacheService:

    def _make_redis(self):
        import fakeredis
        return fakeredis.FakeRedis(decode_responses=True)

    async def test_fill_and_get_next(self):
        """fill_queue + get_next_profile_id возвращают профили в порядке FIFO."""
        import fakeredis.aioredis
        from services.cache_service import CacheService

        redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
        svc = CacheService(redis)

        await svc.fill_queue(user_id=1, profile_ids=[10, 20, 30])

        assert await svc.get_next_profile_id(1) == 10
        assert await svc.get_next_profile_id(1) == 20
        assert await svc.get_next_profile_id(1) == 30

    async def test_get_next_empty_returns_none(self):
        """Пустая очередь возвращает None."""
        import fakeredis.aioredis
        from services.cache_service import CacheService

        redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
        svc = CacheService(redis)

        result = await svc.get_next_profile_id(999)
        assert result is None

    async def test_needs_refill_true_when_empty(self):
        """Пустая очередь требует дозаполнения."""
        import fakeredis.aioredis
        from services.cache_service import CacheService

        redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
        svc = CacheService(redis)

        assert await svc.needs_refill(1) is True

    async def test_needs_refill_false_when_full(self):
        """Очередь с >= 3 элементами не требует дозаполнения."""
        import fakeredis.aioredis
        from services.cache_service import CacheService

        redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
        svc = CacheService(redis)

        await svc.fill_queue(user_id=1, profile_ids=[1, 2, 3, 4, 5])

        assert await svc.needs_refill(1) is False

    async def test_needs_refill_true_when_below_threshold(self):
        """Очередь с < 3 элементами требует дозаполнения."""
        import fakeredis.aioredis
        from services.cache_service import CacheService

        redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
        svc = CacheService(redis)

        await svc.fill_queue(user_id=1, profile_ids=[1, 2])

        assert await svc.needs_refill(1) is True

    async def test_clear_queue(self):
        """clear_queue удаляет все элементы из очереди."""
        import fakeredis.aioredis
        from services.cache_service import CacheService

        redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
        svc = CacheService(redis)

        await svc.fill_queue(user_id=1, profile_ids=[10, 20, 30])
        await svc.clear_queue(user_id=1)

        assert await svc.queue_size(1) == 0

    async def test_different_users_isolated(self):
        """Очереди разных пользователей не пересекаются."""
        import fakeredis.aioredis
        from services.cache_service import CacheService

        redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
        svc = CacheService(redis)

        await svc.fill_queue(user_id=1, profile_ids=[100, 200])
        await svc.fill_queue(user_id=2, profile_ids=[300, 400])

        assert await svc.get_next_profile_id(1) == 100
        assert await svc.get_next_profile_id(2) == 300


# ════════════════════════════════════════════════════════════
# BROWSE ENDPOINT — интеграционные тесты (этап 3/4)
# ════════════════════════════════════════════════════════════

class TestBrowseEndpoint:

    async def test_browse_without_profile_returns_400(self, api):
        """Пользователь без анкеты получает 400."""
        await api.post("/api/v1/users/register", json={
            "telegram_id": 8001,
            "first_name": "БезАнкеты",
        })
        r = await api.get("/api/v1/browse/8001")
        assert r.status_code == 400
        assert "анкету" in r.json()["detail"].lower()

    async def test_browse_unregistered_user_returns_400(self, api):
        """Незарегистрированный пользователь получает 400."""
        r = await api.get("/api/v1/browse/99998888")
        assert r.status_code == 400

    async def test_browse_returns_profile_from_cache(self, api):
        """Browse возвращает анкету при наличии профиля в кэше."""
        import fakeredis.aioredis

        # Создаём просмотрщика
        await api.post("/api/v1/users/register", json={"telegram_id": 8002, "first_name": "Viewer"})
        await api.post("/api/v1/profiles", json={
            "telegram_id": 8002, "name": "Алия", "age": 24,
            "gender": "female", "city": "Алматы",
        })

        # Создаём цель
        await api.post("/api/v1/users/register", json={"telegram_id": 8003, "first_name": "Target"})
        r = await api.post("/api/v1/profiles", json={
            "telegram_id": 8003, "name": "Данияр", "age": 27,
            "gender": "male", "city": "Алматы",
        })
        target_id = r.json()["id"]

        # Мокируем Redis с уже загруженной анкетой в кэше
        fake_redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
        await fake_redis.rpush("browse:8002", str(target_id))

        with patch("api.routes.browse.get_redis", return_value=fake_redis):
            r = await api.get("/api/v1/browse/8002")

        assert r.status_code == 200
        assert r.json()["name"] == "Данияр"

    async def test_browse_empty_cache_no_profiles_returns_404(self, api):
        """Когда нет подходящих анкет, возвращает 404."""
        import fakeredis.aioredis

        await api.post("/api/v1/users/register", json={"telegram_id": 8004, "first_name": "Solo"})
        await api.post("/api/v1/profiles", json={
            "telegram_id": 8004, "name": "Один", "age": 30,
            "gender": "male", "city": "Шымкент",
        })

        # Пустой fakeredis — нет анкет в кэше, ранжировщик вернёт пустой список
        fake_redis = fakeredis.aioredis.FakeRedis(decode_responses=True)

        with patch("api.routes.browse.get_redis", return_value=fake_redis):
            with patch("services.rating_service.RatingService.get_ranked_profiles", new=AsyncMock(return_value=[])):
                r = await api.get("/api/v1/browse/8004")

        assert r.status_code == 404
