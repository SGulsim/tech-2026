from datetime import datetime
from typing import Optional

from sqlalchemy import Float, ForeignKey, Integer, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from db.session import Base


class Profile(Base):
    __tablename__ = "profiles"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True, index=True)
    name: Mapped[Optional[str]]
    age: Mapped[Optional[int]]
    gender: Mapped[Optional[str]]
    city: Mapped[Optional[str]]
    interests: Mapped[Optional[str]] = mapped_column(Text)
    preferences: Mapped[Optional[str]] = mapped_column(Text)
    bio: Mapped[Optional[str]] = mapped_column(Text)
    photo_count: Mapped[int] = mapped_column(Integer, default=0)
    completeness_score: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class ProfilePhoto(Base):
    __tablename__ = "profile_photos"

    id: Mapped[int] = mapped_column(primary_key=True)
    profile_id: Mapped[int] = mapped_column(ForeignKey("profiles.id"), index=True)
    s3_key: Mapped[str]
    url: Mapped[str]
    order_index: Mapped[int] = mapped_column(Integer, default=0)
