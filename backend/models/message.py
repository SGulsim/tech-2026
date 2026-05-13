from datetime import datetime

from sqlalchemy import ForeignKey, Index, func
from sqlalchemy.orm import Mapped, mapped_column

from db.session import Base


class Message(Base):
    __tablename__ = "messages"
    __table_args__ = (
        # для dialog_rate: distinct match_id где sender = user
        Index("ix_messages_sender_match", "sender_user_id", "match_id"),
        # для prime_activity: сообщения пользователя с фильтром по часу
        Index("ix_messages_sender_time", "sender_user_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id"), index=True)
    sender_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
