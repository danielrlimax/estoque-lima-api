from pydantic import BaseModel, Field


class CategoryCreate(BaseModel):
    tenant_id: str
    name: str = Field(min_length=2, max_length=120)
    description: str | None = None
    active: bool = True


class CategoryResponse(BaseModel):
    id: str
    tenant_id: str
    name: str
    description: str | None = None
    active: bool