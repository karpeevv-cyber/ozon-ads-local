from pydantic import BaseModel, EmailStr

from app.schemas.profile import CompanyProfileResponse


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class CurrentUserResponse(BaseModel):
    id: int
    email: EmailStr
    full_name: str
    is_active: bool
    is_admin: bool
    companies: list[CompanyProfileResponse] = []
