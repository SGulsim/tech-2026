from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.logging import get_logger
from models.like import Like
from models.match import Match
from models.profile import Profile
from models.rating import Rating
from models.user import User

logger = get_logger(__name__)


class RatingService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def calculate_and_save(self, profile_id: int) -> Rating:
        result = await self.db.execute(
            select(Profile).where(Profile.id == profile_id)
        )
        profile = result.scalar_one_or_none()
        if not profile:
            raise ValueError(f"Profile {profile_id} not found")

        level1 = profile.completeness_score
        level2 = await self._calc_level2(profile_id, profile.user_id)
        referral_bonus = await self._calc_referral_bonus(profile.user_id)
        # Уровень 3: комбинированный рейтинг
        final = level1 * 0.35 + level2 * 0.50 + referral_bonus * 0.15

        rating_result = await self.db.execute(
            select(Rating).where(Rating.profile_id == profile_id)
        )
        rating = rating_result.scalar_one_or_none()
        if rating:
            rating.level1_score = level1
            rating.level2_score = level2
            rating.referral_bonus = referral_bonus
            rating.final_score = final
            rating.updated_at = datetime.utcnow()
        else:
            rating = Rating(
                profile_id=profile_id,
                level1_score=level1,
                level2_score=level2,
                referral_bonus=referral_bonus,
                final_score=final,
            )
            self.db.add(rating)

        await self.db.flush()
        logger.info(
            "rating_calculated",
            profile_id=profile_id,
            level1=round(level1, 2),
            level2=round(level2, 2),
            referral_bonus=round(referral_bonus, 2),
            final=round(final, 2),
        )
        return rating

    async def _calc_level2(self, profile_id: int, user_id: int) -> float:
        # Количество лайков анкеты
        likes_result = await self.db.execute(
            select(func.count()).where(
                Like.to_profile_id == profile_id,
                Like.is_skip == False,
            )
        )
        likes_count = likes_result.scalar() or 0

        # Количество пропусков
        skips_result = await self.db.execute(
            select(func.count()).where(
                Like.to_profile_id == profile_id,
                Like.is_skip == True,
            )
        )
        skips_count = skips_result.scalar() or 0

        total = likes_count + skips_count
        # Соотношение лайков и пропусков
        like_ratio = likes_count / total if total > 0 else 0.5

        # Частота взаимных лайков (мэтчей)
        matches_result = await self.db.execute(
            select(func.count()).where(
                (Match.user1_id == user_id) | (Match.user2_id == user_id)
            )
        )
        match_count = matches_result.scalar() or 0
        match_rate = min(match_count / max(likes_count, 1), 1.0)

        # Активность за последние 7 дней
        week_ago = datetime.utcnow() - timedelta(days=7)
        recent_result = await self.db.execute(
            select(func.count()).where(
                Like.to_profile_id == profile_id,
                Like.is_skip == False,
                Like.created_at >= week_ago,
            )
        )
        recent_likes = recent_result.scalar() or 0
        recent_bonus = min(recent_likes * 2, 20)

        score = (
            min(likes_count * 1.5, 30)  # вес лайков (макс 30)
            + like_ratio * 30           # соотношение лайков/пропусков (макс 30)
            + match_rate * 20           # частота мэтчей (макс 20)
            + recent_bonus              # недавняя активность (макс 20)
        )
        return min(score, 100.0)

    async def _calc_referral_bonus(self, user_id: int) -> float:
        # Реферальная система: +5 за каждого приглашённого (макс 25)
        result = await self.db.execute(
            select(func.count()).where(User.referrer_id == user_id)
        )
        referrals = result.scalar() or 0
        return min(referrals * 5.0, 25.0)

    async def get_ranked_profiles(
        self,
        for_user_id: int,
        own_profile_id: int,
        gender_pref: Optional[str],
        limit: int = 10,
    ) -> list[int]:
        # Исключаем уже просмотренные анкеты
        seen_result = await self.db.execute(
            select(Like.to_profile_id).where(Like.from_user_id == for_user_id)
        )
        seen_ids = {row[0] for row in seen_result.all()}
        seen_ids.add(own_profile_id)

        query = (
            select(Profile.id, Rating.final_score)
            .outerjoin(Rating, Rating.profile_id == Profile.id)
            .where(Profile.id.not_in(seen_ids))
        )
        if gender_pref and gender_pref != "any":
            query = query.where(Profile.gender == gender_pref)

        query = query.order_by(Rating.final_score.desc().nulls_last()).limit(limit)

        result = await self.db.execute(query)
        return [row[0] for row in result.all()]
