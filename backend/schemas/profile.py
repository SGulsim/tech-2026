from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class ProfileCreate(BaseModel):
    telegram_id: int
    name: str
    age: int
    gender: str
    city: str
    interests: Optional[str] = None
    preferences: Optional[str] = None
    bio: Optional[str] = None


class ProfileUpdate(BaseModel):
    name: Optional[str] = None
    age: Optional[int] = None
    gender: Optional[str] = None
    city: Optional[str] = None
    interests: Optional[str] = None
    preferences: Optional[str] = None
    bio: Optional[str] = None


class ProfileResponse(BaseModel):
    id: int
    user_id: int
    telegram_id: Optional[int] = None
    name: Optional[str]
    age: Optional[int]
    gender: Optional[str]
    city: Optional[str]
    interests: Optional[str]
    preferences: Optional[str]
    bio: Optional[str]
    photo_count: int
    completeness_score: float
    photos: list[str] = []
    rating_score: Optional[float] = None
    created_at: datetime

    model_config = {"from_attributes": True}
