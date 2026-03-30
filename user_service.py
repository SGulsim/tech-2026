from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.logging import get_logger
from models.user import User
from schemas.user import UserCreate, UserResponse

logger = get_logger(__name__)


class UserService:
    """
    Сервис для работы с пользователями.
    Содержит бизнес-логику регистрации и поиска.
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_telegram_id(self, telegram_id: int) -> User | None:
        """Найти пользователя по Telegram ID."""
        result = await self.db.execute(
            select(User).where(User.telegram_id == telegram_id)
        )
        return result.scalar_one_or_none()

    async def register(self, data: UserCreate) -> UserResponse:
        """
        Регистрация пользователя.
        Если пользователь уже существует — возвращает его без изменений.
        Если нет — создаёт нового.

        Логика реферала:
        Если передан referrer_telegram_id, находим реферера по telegram_id
        и сохраняем его внутренний id как referrer_id.
        """
        # Проверяем, не зарегистрирован ли уже
        existing = await self.get_by_telegram_id(data.telegram_id)
        if existing:
            logger.info("user_already_exists", telegram_id=data.telegram_id)
            return UserResponse.model_validate(existing)

        # Находим реферера, если указан
        referrer_id: int | None = None
        if data.referrer_telegram_id:
            referrer = await self.get_by_telegram_id(data.referrer_telegram_id)
            if referrer:
                referrer_id = referrer.id
                logger.info(
                    "referrer_found",
                    referrer_telegram_id=data.referrer_telegram_id,
                    referrer_id=referrer_id,
                )

        # Создаём нового пользователя
        user = User(
            telegram_id=data.telegram_id,
            username=data.username,
            first_name=data.first_name,
            referrer_id=referrer_id,
        )
        self.db.add(user)
        await self.db.flush()   # получаем id до commit

        logger.info(
            "user_registered",
            telegram_id=data.telegram_id,
            user_id=user.id,
            referrer_id=referrer_id,
        )

        response = UserResponse.model_validate(user)
        response.is_new = True
        return response

    async def get_or_create(self, data: UserCreate) -> UserResponse:
        """Shortcut: вернуть существующего или создать нового."""
        existing = await self.get_by_telegram_id(data.telegram_id)
        if existing:
            return UserResponse.model_validate(existing)
        return await self.register(data)
