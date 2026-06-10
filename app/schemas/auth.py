from pydantic import BaseModel, EmailStr, Field


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6)


class AuthUserResponse(BaseModel):
    id: str
    email: str | None = None


class LoginResponse(BaseModel):
    authenticated: bool
    user: AuthUserResponse