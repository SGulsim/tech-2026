import uuid

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from core.minio_client import upload_photo
from core.redis_client import get_redis
from db.session import get_db
from schemas.profile import ProfileCreate, ProfileResponse, ProfileUpdate
from services.cache_service import CacheService
from services.profile_service import ProfileService
from services.rating_service import RatingService

router = APIRouter(prefix="/api/v1/profiles", tags=["profiles"])


@router.post("", response_model=ProfileResponse, status_code=201)
async def create_profile(data: ProfileCreate, db: AsyncSession = Depends(get_db)):
    svc = ProfileService(db)
    try:
        profile = await svc.create(data)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    # Инициализируем рейтинг сразу после создания
    rating_svc = RatingService(db)
    await rating_svc.calculate_and_save(profile.id)
    return profile


@router.get("/{telegram_id}", response_model=ProfileResponse)
async def get_profile(telegram_id: int, db: AsyncSession = Depends(get_db)):
    svc = ProfileService(db)
    profile = await svc.get_by_telegram_id(telegram_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    return profile


@router.put("/{telegram_id}", response_model=ProfileResponse)
async def update_profile(
    telegram_id: int, data: ProfileUpdate, db: AsyncSession = Depends(get_db)
):
    svc = ProfileService(db)
    profile = await svc.update(telegram_id, data)
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    # Пересчитываем рейтинг и сбрасываем кэш просмотра
    rating_svc = RatingService(db)
    await rating_svc.calculate_and_save(profile.id)
    cache_svc = CacheService(get_redis())
    await cache_svc.clear_queue(telegram_id)
    return profile


@router.delete("/{telegram_id}", status_code=204)
async def delete_profile(telegram_id: int, db: AsyncSession = Depends(get_db)):
    svc = ProfileService(db)
    deleted = await svc.delete(telegram_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Profile not found")


@router.post("/{telegram_id}/photos", response_model=ProfileResponse)
async def upload_profile_photo(
    telegram_id: int,
    photo: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    data = await photo.read()
    key = f"{telegram_id}/{uuid.uuid4()}.jpg"
    url = await upload_photo(key, data, photo.content_type or "image/jpeg")

    svc = ProfileService(db)
    profile = await svc.add_photo(telegram_id, key, url)
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")

    # Пересчитываем рейтинг после добавления фото
    rating_svc = RatingService(db)
    await rating_svc.calculate_and_save(profile.id)
    return profile
