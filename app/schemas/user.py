from pydantic import BaseModel, EmailStr
from uuid import UUID
from typing import Optional


class UserCreate(BaseModel):
    email: EmailStr
    password: str
    full_name: Optional[str] = None


class UserRead(BaseModel):
    id: UUID
    email: EmailStr
    full_name: Optional[str] = None

    class Config:
        from_attributes = True
