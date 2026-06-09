from pydantic import BaseModel


class SubscriptionStatusResponse(BaseModel):
    tenant_id: str
    status: str
    is_active: bool
    plan_code: str | None = None
    plan_name: str | None = None
    trial_ends_at: str | None = None
    current_period_end: str | None = None
    asaas_customer_id: str | None = None
    asaas_subscription_id: str | None = None