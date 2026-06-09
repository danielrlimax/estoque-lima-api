from decimal import Decimal

from pydantic import BaseModel, EmailStr, Field


class AdminMeResponse(BaseModel):
    is_admin: bool
    email: str | None = None


class AdminPlatformSummaryResponse(BaseModel):
    total_tenants: int
    active_tenants: int
    trialing_tenants: int
    suspended_tenants: int
    canceled_tenants: int
    banned_tenants: int
    total_subscriptions: int
    active_subscriptions: int
    trialing_subscriptions: int
    past_due_subscriptions: int
    canceled_subscriptions: int
    total_coupons: int
    active_coupons: int
    total_asaas_events: int


class AdminTenantCreateRequest(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    slug: str | None = Field(default=None, max_length=80)
    email: EmailStr | None = None
    phone: str | None = None
    document: str | None = None
    status: str = "trialing"
    owner_email: EmailStr | None = None


class AdminTenantResponse(BaseModel):
    id: str
    name: str
    slug: str
    email: str | None = None
    phone: str | None = None
    document: str | None = None
    status: str
    created_at: str


class AdminUpdateTenantStatusRequest(BaseModel):
    status: str


class AdminAddTenantMemberRequest(BaseModel):
    email: EmailStr
    role: str = "owner"


class AdminTenantMemberResponse(BaseModel):
    id: str
    tenant_id: str
    user_id: str
    role: str
    active: bool


class AdminSubscriptionResponse(BaseModel):
    id: str
    tenant_id: str
    tenant_name: str | None = None
    status: str
    provider: str
    asaas_customer_id: str | None = None
    asaas_subscription_id: str | None = None
    trial_ends_at: str | None = None
    current_period_end: str | None = None
    created_at: str


class AdminUpdateSubscriptionStatusRequest(BaseModel):
    status: str


class AdminCouponCreateRequest(BaseModel):
    code: str = Field(min_length=2, max_length=80)
    description: str | None = None
    type: str
    value: Decimal = Field(gt=0)
    max_uses: int | None = Field(default=None, ge=1)
    valid_from: str | None = None
    valid_until: str | None = None
    active: bool = True


class AdminCouponUpdateRequest(BaseModel):
    description: str | None = None
    type: str | None = None
    value: Decimal | None = Field(default=None, gt=0)
    max_uses: int | None = Field(default=None, ge=1)
    valid_from: str | None = None
    valid_until: str | None = None
    active: bool | None = None


class AdminCouponResponse(BaseModel):
    id: str
    code: str
    description: str | None = None
    type: str
    value: Decimal
    active: bool
    max_uses: int | None = None
    used_count: int
    valid_from: str | None = None
    valid_until: str | None = None
    created_at: str


class AdminAsaasEventResponse(BaseModel):
    id: str
    event_id: str | None = None
    event_type: str | None = None
    payment_id: str | None = None
    subscription_id: str | None = None
    customer_id: str | None = None
    processed: bool
    processed_at: str | None = None
    created_at: str