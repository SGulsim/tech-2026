from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.redis_client import get_redis
from db.session import get_db
from models.rating import Rating
from models.user import User
from schemas.profile import ProfileResponse
from services.cache_service import CacheService
from services.profile_service import ProfileService
from services.rating_service import RatingService

router = APIRouter(prefix="/api/v1/browse", tags=["browse"])


@router.get("/{telegram_id}", response_model=ProfileResponse)
async def get_next_profile(telegram_id: int, db: AsyncSession = Depends(get_db)):
    profile_svc = ProfileService(db)
    rating_svc = RatingService(db)
    cache_svc = CacheService(get_redis())

    own_profile = await profile_svc.get_by_telegram_id(telegram_id)
    if not own_profile:
        raise HTTPException(status_code=400, detail="Сначала создайте анкету")

    user_result = await db.execute(select(User).where(User.telegram_id == telegram_id))
    user = user_result.scalar_one_or_none()

    # Определяем предпочтение по полу из анкеты
    gender_pref: str | None = None
    if own_profile.preferences:
        prefs_lower = own_profile.preferences.lower()
        if "male" in prefs_lower or "парн" in prefs_lower or "муж" in prefs_lower:
            gender_pref = "male"
        elif "female" in prefs_lower or "девуш" in prefs_lower or "жен" in prefs_lower:
            gender_pref = "female"

    # Подгружаем следующую порцию анкет в кэш если нужно
    if await cache_svc.needs_refill(telegram_id):
        ranked_ids = await rating_svc.get_ranked_profiles(
            for_user_id=user.id,
            own_profile_id=own_profile.id,
            gender_pref=gender_pref,
            limit=10,
        )
        await cache_svc.fill_queue(telegram_id, ranked_ids)

    # Берём следующую анкету из кэша (до 5 попыток на случай удалённых)
    for _ in range(5):
        next_id = await cache_svc.get_next_profile_id(telegram_id)
        if next_id is None:
            raise HTTPException(status_code=404, detail="Анкеты закончились")

        profile = await profile_svc.get_by_id(next_id)
        if not profile:
            continue  # анкета была удалена, берём следующую

        # Добавляем итоговый рейтинг в ответ
        rating_result = await db.execute(
            select(Rating).where(Rating.profile_id == next_id)
        )
        rating = rating_result.scalar_one_or_none()
        if rating:
            profile.rating_score = rating.final_score

        return profile

    raise HTTPException(status_code=404, detail="Анкеты закончились")
