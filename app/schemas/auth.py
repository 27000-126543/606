from pydantic import BaseModel, Field, EmailStr
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone
from uuid import UUID


class Token(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class TokenPayload(BaseModel):
    sub: Optional[str] = None
    type: Optional[str] = None


class UserLogin(BaseModel):
    username: str = Field(..., min_length=1, max_length=50)
    password: str = Field(..., min_length=1, max_length=255)


class UserCreate(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=6, max_length=255)
    real_name: str = Field(..., min_length=2, max_length=100)
    email: EmailStr
    phone: Optional[str] = Field(None, max_length=20)
    role: str = Field("operator", pattern="^(supervisor|operator)$")
    team_ids: Optional[List[str]] = None


class UserUpdate(BaseModel):
    real_name: Optional[str] = Field(None, max_length=100)
    email: Optional[EmailStr] = None
    phone: Optional[str] = Field(None, max_length=20)
    role: Optional[str] = Field(None, pattern="^(supervisor|operator)$")
    is_active: Optional[bool] = None


class UserResponse(BaseModel):
    id: UUID
    username: str
    real_name: str
    email: str
    phone: Optional[str]
    role: str
    is_active: bool
    last_login_at: Optional[datetime]
    created_at: datetime
    teams: Optional[List[Dict[str, Any]]] = None

    class Config:
        from_attributes = True


class TeamCreate(BaseModel):
    name: str = Field(..., max_length=100)
    description: Optional[str] = None
    parent_team_id: Optional[str] = None
    leader_id: Optional[str] = None
    notification_emails: Optional[List[str]] = None


class TeamResponse(BaseModel):
    id: UUID
    name: str
    description: Optional[str]
    parent_team_id: Optional[UUID]
    leader_id: Optional[UUID]
    notification_emails: Optional[List[str]]
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True


class LoginResponse(BaseModel):
    code: int = 200
    message: str = "登录成功"
    data: Token


class UserListResponse(BaseModel):
    code: int = 200
    message: str = "success"
    data: List[UserResponse]
    total: int


class TeamListResponse(BaseModel):
    code: int = 200
    message: str = "success"
    data: List[TeamResponse]
    total: int
