from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class UserRegister(BaseModel):
    """Public registration schema. Role is NOT accepted from the client;
    all public registrations are created with role="user" server-side."""
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class AdminUserCreate(BaseModel):
    """Admin-only user creation schema. Role selection is permitted here
    because the endpoint is protected by require_role(["admin"])."""
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    role: str = Field(default="user", pattern="^(admin|analyst|user)$")


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserOut(BaseModel):
    id: int
    email: str
    role: str
    created_at: datetime

    class Config:
        from_attributes = True


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserRoleUpdate(BaseModel):
    role: str = Field(pattern="^(admin|analyst|user)$")
