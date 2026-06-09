from pydantic import BaseModel, EmailStr, Field


class StartSubscriptionRequest(BaseModel):
    tenant_id: str
    customer_name: str = Field(min_length=2, max_length=120)
    customer_email: EmailStr
    cpf_cnpj: str | None = None
    phone: str | None = None
    billing_type: str = "PIX"
    coupon_code: str | None = None


class StartSubscriptionResponse(BaseModel):
    tenant_id: str
    asaas_customer_id: str
    asaas_subscription_id: str
    status: str
    original_price: float
    discount_amount: float
    final_price: float
    coupon_code: str | None = None