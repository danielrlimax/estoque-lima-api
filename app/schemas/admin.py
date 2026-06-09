from pydantic import BaseModel


class AdminTenantResponse(BaseModel):
    id: str
    name: str
    slug: str
    email: str | None = None
    phone: str | None = None
    document: str | None = None
    status: str
    created_at: str


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


class AdminUpdateTenantStatusRequest(BaseModel):
    status: str


class AdminUpdateSubscriptionStatusRequest(BaseModel):
    status: str


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


class AdminPlatformSummaryResponse(BaseModel):
    total_tenants: int
    active_tenants: int
    trialing_tenants: int
    suspended_tenants: int
    canceled_tenants: int
    total_subscriptions: int
    active_subscriptions: int
    trialing_subscriptions: int
    past_due_subscriptions: int
    canceled_subscriptions: int