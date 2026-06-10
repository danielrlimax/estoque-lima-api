from fastapi import HTTPException, status

from app.db.supabase_client import get_supabase_admin


ACTIVE_SUBSCRIPTION_STATUSES = {
    "active",
    "trialing",
    "paid",
    "manual",
}


def ensure_tenant_access_is_active(tenant_id: str):
    supabase = get_supabase_admin()

    try:
        tenant_response = (
            supabase
            .table("tenants")
            .select("id, status")
            .eq("id", tenant_id)
            .limit(1)
            .execute()
        )

        if not tenant_response.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Estabelecimento não encontrado.",
            )

        tenant = tenant_response.data[0]
        tenant_status = tenant.get("status")

        if tenant_status == "banned":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Este estabelecimento foi banido da plataforma.",
            )

        if tenant_status in {"suspended", "canceled", "cancelled", "inactive"}:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Este estabelecimento está bloqueado. Regularize o acesso.",
            )

        subscription_response = (
            supabase
            .table("subscriptions")
            .select("id, status")
            .eq("tenant_id", tenant_id)
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )

        if not subscription_response.data:
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail="Assinatura não encontrada. Configure a assinatura para continuar.",
            )

        subscription = subscription_response.data[0]
        subscription_status = subscription.get("status")

        if subscription_status not in ACTIVE_SUBSCRIPTION_STATUSES:
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail="Assinatura inativa. Regularize sua assinatura para continuar usando o sistema.",
            )

        return True

    except HTTPException:
        raise
    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro ao validar assinatura: {str(error)}",
        )