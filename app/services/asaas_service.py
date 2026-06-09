import httpx

from app.core.config import settings


class AsaasService:
    def __init__(self):
        self.base_url = settings.ASAAS_BASE_URL.rstrip("/")
        self.headers = {
            "accept": "application/json",
            "content-type": "application/json",
            "access_token": settings.ASAAS_API_KEY,
        }

    async def create_customer(
        self,
        name: str,
        email: str,
        cpf_cnpj: str | None = None,
        phone: str | None = None,
    ) -> dict:
        payload = {
            "name": name,
            "email": email,
        }

        if cpf_cnpj:
            payload["cpfCnpj"] = cpf_cnpj

        if phone:
            payload["mobilePhone"] = phone

        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                f"{self.base_url}/customers",
                headers=self.headers,
                json=payload,
            )

        response.raise_for_status()
        return response.json()

    async def create_subscription(
        self,
        customer_id: str,
        value: float,
        billing_type: str = "PIX",
        cycle: str = "MONTHLY",
        description: str = "Assinatura Estoque SaaS",
    ) -> dict:
        payload = {
            "customer": customer_id,
            "billingType": billing_type,
            "cycle": cycle,
            "value": value,
            "nextDueDate": self._next_due_date(),
            "description": description,
        }

        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                f"{self.base_url}/subscriptions",
                headers=self.headers,
                json=payload,
            )

        response.raise_for_status()
        return response.json()

    async def get_subscription(self, subscription_id: str) -> dict:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(
                f"{self.base_url}/subscriptions/{subscription_id}",
                headers=self.headers,
            )

        response.raise_for_status()
        return response.json()

    def _next_due_date(self) -> str:
        from datetime import date, timedelta

        return (date.today() + timedelta(days=1)).isoformat()