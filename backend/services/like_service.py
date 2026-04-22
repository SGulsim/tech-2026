from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.logging import get_logger
from core.rabbitmq import QUEUE_NOTIFICATIONS, publish
from models.like import Like
from models.match import Match
from models.profile import Profile
from models.user import User
from services.rating_service import RatingService

logger = get_logger(__name__)


class LikeService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def process_action(
        self, from_telegram_id: int, to_profile_id: int, is_skip: bool
    ) -> Optional[dict]:
        user_result = await self.db.execute(
            select(User).where(User.telegram_id == from_telegram_id)
        )
        user = user_result.scalar_one_or_none()
        if not user:
            logger.warning("like_user_not_found", telegram_id=from_telegram_id)
            return None

        # Пропускаем дублирующиеся действия
        existing = await self.db.execute(
            select(Like).where(
                Like.from_user_id == user.id,
                Like.to_profile_id == to_profile_id,
            )
        )
        if existing.scalar_one_or_none():
            return None

        like = Like(from_user_id=user.id, to_profile_id=to_profile_id, is_skip=is_skip)
        self.db.add(like)
        await self.db.flush()

        # Пересчитываем рейтинг целевой анкеты
        rating_svc = RatingService(self.db)
        await rating_svc.calculate_and_save(to_profile_id)

        if is_skip:
            logger.info("profile_skipped", by=user.id, profile=to_profile_id)
            return None

        logger.info("profile_liked", by=user.id, profile=to_profile_id)

        # Проверяем взаимный лайк (мэтч)
        target_profile_result = await self.db.execute(
            select(Profile).where(Profile.id == to_profile_id)
        )
        target_profile = target_profile_result.scalar_one_or_none()
        if not target_profile:
            return None

        own_profile_result = await self.db.execute(
            select(Profile).where(Profile.user_id == user.id)
        )
        own_profile = own_profile_result.scalar_one_or_none()
        if not own_profile:
            return None

        mutual_result = await self.db.execute(
            select(Like).where(
                Like.from_user_id == target_profile.user_id,
                Like.to_profile_id == own_profile.id,
                Like.is_skip == False,
            )
        )
        if not mutual_result.scalar_one_or_none():
            return None

        # Избегаем дублирующихся мэтчей
        dup_result = await self.db.execute(
            select(Match).where(
                ((Match.user1_id == user.id) & (Match.user2_id == target_profile.user_id))
                | ((Match.user1_id == target_profile.user_id) & (Match.user2_id == user.id))
            )
        )
        if dup_result.scalar_one_or_none():
            return None

        match = Match(user1_id=user.id, user2_id=target_profile.user_id)
        self.db.add(match)
        await self.db.flush()

        target_user_result = await self.db.execute(
            select(User).where(User.id == target_profile.user_id)
        )
        target_user = target_user_result.scalar_one_or_none()

        match_event = {
            "type": "match",
            "user1_telegram_id": from_telegram_id,
            "user2_telegram_id": target_user.telegram_id if target_user else None,
            "user1_name": own_profile.name or "Аноним",
            "user2_name": target_profile.name or "Аноним",
        }
        await publish(QUEUE_NOTIFICATIONS, match_event)
        logger.info("match_created", user1=user.id, user2=target_profile.user_id)
        return match_event
