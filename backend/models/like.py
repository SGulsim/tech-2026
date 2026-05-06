from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, Index, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from db.session import Base


class Like(Base):
    __tablename__ = "likes"
    __table_args__ = (
        UniqueConstraint("from_user_id", "to_profile_id"),
        # для подсчёта лайков/скипов в rating_service
        Index("ix_likes_profile_skip", "to_profile_id", "is_skip"),
        # для подсчёта недавних лайков (last 7 days)
        Index("ix_likes_profile_skip_time", "to_profile_id", "is_skip", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    from_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    to_profile_id: Mapped[int] = mapped_column(ForeignKey("profiles.id"), index=True)
    is_skip: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
