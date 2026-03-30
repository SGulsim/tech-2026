from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class UserCreate(BaseModel):
    telegram_id: int
    username: Optional[str] = None
    first_name: Optional[str] = None
    referrer_telegram_id: Optional[int] = None


class UserResponse(BaseModel):
    id: int
    telegram_id: int
    username: Optional[str]
    first_name: Optional[str]
    referrer_id: Optional[int]
    created_at: datetime
    is_new: bool = False

    model_config = {"from_attributes": True}
