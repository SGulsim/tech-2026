from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Index, func
from sqlalchemy.orm import Mapped, mapped_column

from db.session import Base


class Rating(Base):
    __tablename__ = "ratings"
    __table_args__ = (
        # для ORDER BY final_score DESC в get_ranked_profiles
        Index("ix_ratings_final_score", "final_score"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    profile_id: Mapped[int] = mapped_column(ForeignKey("profiles.id"), unique=True, index=True)
    level1_score: Mapped[float] = mapped_column(Float, default=0.0)
    level2_score: Mapped[float] = mapped_column(Float, default=0.0)
    referral_bonus: Mapped[float] = mapped_column(Float, default=0.0)
    final_score: Mapped[float] = mapped_column(Float, default=0.0)
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
