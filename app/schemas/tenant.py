from pydantic import BaseModel, Field, EmailStr


class TenantCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    slug: str = Field(min_length=2, max_length=80)
    document: str | None = None
    phone: str | None = None
    email: EmailStr | None = None


class TenantResponse(BaseModel):
    id: str
    name: str
    slug: str
    document: str | None = None
    phone: str | None = None
    email: str | None = None
    status: str
    role: str | None = None