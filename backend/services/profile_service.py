from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.logging import get_logger
from models.profile import Profile, ProfilePhoto
from models.user import User
from schemas.profile import ProfileCreate, ProfileResponse, ProfileUpdate

logger = get_logger(__name__)


def _calc_completeness(profile: Profile) -> float:
    score = 0.0
    if profile.name:
        score += 10
    if profile.age:
        score += 10
    if profile.gender:
        score += 5
    if profile.city:
        score += 10
    if profile.bio and len(profile.bio) > 10:
        score += 15
    if profile.interests:
        score += 15
    if profile.preferences:
        score += 10
    if profile.photo_count >= 1:
        score += 15
    if profile.photo_count >= 3:
        score += 10
    return min(score, 100.0)


class ProfileService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def _get_user(self, telegram_id: int) -> Optional[User]:
        result = await self.db.execute(
            select(User).where(User.telegram_id == telegram_id)
        )
        return result.scalar_one_or_none()

    async def get_by_telegram_id(self, telegram_id: int) -> Optional[ProfileResponse]:
        user = await self._get_user(telegram_id)
        if not user:
            return None
        result = await self.db.execute(
            select(Profile).where(Profile.user_id == user.id)
        )
        profile = result.scalar_one_or_none()
        if not profile:
            return None
        return await self._to_response(profile, telegram_id=telegram_id)

    async def get_by_id(self, profile_id: int) -> Optional[ProfileResponse]:
        result = await self.db.execute(
            select(Profile).where(Profile.id == profile_id)
        )
        profile = result.scalar_one_or_none()
        if not profile:
            return None
        user_result = await self.db.execute(
            select(User).where(User.id == profile.user_id)
        )
        user = user_result.scalar_one_or_none()
        return await self._to_response(profile, telegram_id=user.telegram_id if user else None)

    async def create(self, data: ProfileCreate) -> ProfileResponse:
        user = await self._get_user(data.telegram_id)
        if not user:
            raise ValueError(f"User {data.telegram_id} not found")

        existing = await self.db.execute(
            select(Profile).where(Profile.user_id == user.id)
        )
        if existing.scalar_one_or_none():
            raise ValueError("Profile already exists")

        profile = Profile(
            user_id=user.id,
            name=data.name,
            age=data.age,
            gender=data.gender,
            city=data.city,
            interests=data.interests,
            preferences=data.preferences,
            bio=data.bio,
        )
        profile.completeness_score = _calc_completeness(profile)
        self.db.add(profile)
        await self.db.flush()

        logger.info("profile_created", profile_id=profile.id, user_id=user.id)
        return await self._to_response(profile, telegram_id=data.telegram_id)

    async def update(self, telegram_id: int, data: ProfileUpdate) -> Optional[ProfileResponse]:
        user = await self._get_user(telegram_id)
        if not user:
            return None
        result = await self.db.execute(
            select(Profile).where(Profile.user_id == user.id)
        )
        profile = result.scalar_one_or_none()
        if not profile:
            return None

        for field, value in data.model_dump(exclude_none=True).items():
            setattr(profile, field, value)

        profile.completeness_score = _calc_completeness(profile)
        await self.db.flush()

        logger.info("profile_updated", profile_id=profile.id)
        return await self._to_response(profile, telegram_id=telegram_id)

    async def delete(self, telegram_id: int) -> bool:
        user = await self._get_user(telegram_id)
        if not user:
            return False
        result = await self.db.execute(
            select(Profile).where(Profile.user_id == user.id)
        )
        profile = result.scalar_one_or_none()
        if not profile:
            return False
        await self.db.delete(profile)
        await self.db.flush()
        return True

    async def add_photo(self, telegram_id: int, s3_key: str, url: str) -> Optional[ProfileResponse]:
        user = await self._get_user(telegram_id)
        if not user:
            return None
        result = await self.db.execute(
            select(Profile).where(Profile.user_id == user.id)
        )
        profile = result.scalar_one_or_none()
        if not profile:
            return None

        photo = ProfilePhoto(
            profile_id=profile.id,
            s3_key=s3_key,
            url=url,
            order_index=profile.photo_count,
        )
        profile.photo_count += 1
        profile.completeness_score = _calc_completeness(profile)
        self.db.add(photo)
        await self.db.flush()

        return await self._to_response(profile, telegram_id=telegram_id)

    async def _to_response(self, profile: Profile, telegram_id: Optional[int] = None) -> ProfileResponse:
        photos_result = await self.db.execute(
            select(ProfilePhoto)
            .where(ProfilePhoto.profile_id == profile.id)
            .order_by(ProfilePhoto.order_index)
        )
        photos = photos_result.scalars().all()

        resp = ProfileResponse.model_validate(profile)
        resp.telegram_id = telegram_id
        resp.photos = [p.url for p in photos]
        return resp
