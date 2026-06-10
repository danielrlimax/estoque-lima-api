from fastapi import HTTPException, status

from app.db.supabase_client import get_supabase_admin


ACTIVE_SUBSCRIPTION_STATUSES = [
    "active",
    "trialing",
    "paid",
    "manual",
]


def get_tenant_current_subscription(tenant_id: str) -> dict | None:
    try:
        supabase = get_supabase_admin()

        response = (
            supabase
            .table("subscriptions")
            .select("*")
            .eq("tenant_id", tenant_id)
            .in_("status", ACTIVE_SUBSCRIPTION_STATUSES)
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )

        if not response.data:
            return None

        return response.data[0]

    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro ao consultar assinatura do estabelecimento: {str(error)}",
        )


def get_plan(plan_id: str) -> dict | None:
    try:
        supabase = get_supabase_admin()

        response = (
            supabase
            .table("plans")
            .select("*")
            .eq("id", plan_id)
            .limit(1)
            .execute()
        )

        if not response.data:
            return None

        return response.data[0]

    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro ao consultar plano: {str(error)}",
        )


def get_tenant_plan(tenant_id: str) -> dict:
    subscription = get_tenant_current_subscription(tenant_id)

    if not subscription:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail="Este estabelecimento não possui assinatura ativa.",
        )

    plan_id = subscription.get("plan_id")

    if not plan_id:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail="A assinatura atual não possui plano vinculado.",
        )

    plan = get_plan(plan_id)

    if not plan:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail="Plano da assinatura não encontrado.",
        )

    if plan.get("active") is False:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail="O plano atual está inativo. Altere o plano para continuar.",
        )

    return plan


def normalize_limit(value) -> int | None:
    if value is None:
        return None

    try:
        number = int(value)
    except Exception:
        return None

    if number <= 0:
        return None

    return number


def get_active_products_count(tenant_id: str) -> int:
    try:
        supabase = get_supabase_admin()

        try:
            response = (
                supabase
                .table("products")
                .select("id")
                .eq("tenant_id", tenant_id)
                .eq("active", True)
                .execute()
            )

            return len(response.data or [])

        except Exception:
            response = (
                supabase
                .table("products")
                .select("id")
                .eq("tenant_id", tenant_id)
                .execute()
            )

            return len(response.data or [])

    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro ao contar produtos do estabelecimento: {str(error)}",
        )


def get_tenant_members_count(tenant_id: str) -> int:
    try:
        supabase = get_supabase_admin()

        try:
            response = (
                supabase
                .table("tenant_members")
                .select("id")
                .eq("tenant_id", tenant_id)
                .eq("active", True)
                .execute()
            )

            return len(response.data or [])

        except Exception:
            response = (
                supabase
                .table("tenant_members")
                .select("id")
                .eq("tenant_id", tenant_id)
                .execute()
            )

            return len(response.data or [])

    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro ao contar usuários do estabelecimento: {str(error)}",
        )


def ensure_product_limit_not_exceeded(tenant_id: str):
    plan = get_tenant_plan(tenant_id)

    max_products = normalize_limit(plan.get("max_products"))

    if max_products is None:
        return

    active_products_count = get_active_products_count(tenant_id)

    if active_products_count >= max_products:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=(
                f"Limite de produtos atingido para o plano {plan.get('name')}. "
                f"Seu plano permite até {max_products} produtos ativos."
            ),
        )


def ensure_user_limit_not_exceeded(tenant_id: str):
    plan = get_tenant_plan(tenant_id)

    max_users = normalize_limit(plan.get("max_users"))

    if max_users is None:
        return

    members_count = get_tenant_members_count(tenant_id)

    if members_count >= max_users:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=(
                f"Limite de usuários atingido para o plano {plan.get('name')}. "
                f"Seu plano permite até {max_users} usuários no estabelecimento."
            ),
        )


def get_plan_usage(tenant_id: str) -> dict:
    plan = get_tenant_plan(tenant_id)

    max_products = normalize_limit(plan.get("max_products"))
    max_users = normalize_limit(plan.get("max_users"))

    products_count = get_active_products_count(tenant_id)
    users_count = get_tenant_members_count(tenant_id)

    return {
        "tenant_id": tenant_id,
        "plan": {
            "id": plan.get("id"),
            "code": plan.get("code"),
            "name": plan.get("name"),
            "price_monthly": plan.get("price_monthly"),
            "max_products": max_products,
            "max_users": max_users,
        },
        "usage": {
            "products": products_count,
            "users": users_count,
        },
        "limits": {
            "products": max_products,
            "users": max_users,
        },
        "remaining": {
            "products": None if max_products is None else max(max_products - products_count, 0),
            "users": None if max_users is None else max(max_users - users_count, 0),
        },
    }