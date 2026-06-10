from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from app.core.audit import write_audit_log
from app.core.config import get_platform_admin_emails
from app.core.security import get_current_user
from app.db.supabase_client import get_supabase_admin

router = APIRouter(prefix="/admin/plans", tags=["Admin Plans"])


class PlanCreateRequest(BaseModel):
    code: str = Field(min_length=2, max_length=80)
    name: str = Field(min_length=2, max_length=120)
    description: str | None = None
    price_monthly: Decimal = Field(ge=0)
    features: list[str] = []
    max_products: int | None = Field(default=None, ge=0)
    max_users: int | None = Field(default=None, ge=0)
    active: bool = True


class PlanUpdateRequest(BaseModel):
    code: str | None = Field(default=None, min_length=2, max_length=80)
    name: str | None = Field(default=None, min_length=2, max_length=120)
    description: str | None = None
    price_monthly: Decimal | None = Field(default=None, ge=0)
    features: list[str] | None = None
    max_products: int | None = Field(default=None, ge=0)
    max_users: int | None = Field(default=None, ge=0)
    active: bool | None = None


def require_platform_admin(current_user: dict):
    allowed_emails = get_platform_admin_emails()
    email = (current_user.get("email") or "").strip().lower()

    if email not in allowed_emails:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acesso permitido apenas para administrador da plataforma.",
        )


def serialize_plan_payload(payload: dict[str, Any]):
    data = {}

    for key, value in payload.items():
        if value is None:
            continue

        if isinstance(value, Decimal):
            data[key] = str(value)
        else:
            data[key] = value

    return data


@router.get("")
def list_plans(
    current_user: dict = Depends(get_current_user),
):
    require_platform_admin(current_user)

    try:
        supabase = get_supabase_admin()

        response = (
            supabase
            .table("plans")
            .select("*")
            .order("price_monthly", desc=False)
            .execute()
        )

        return response.data or []

    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(error),
        )


@router.post("")
def create_plan(
    payload: PlanCreateRequest,
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    require_platform_admin(current_user)

    try:
        supabase = get_supabase_admin()

        existing_response = (
            supabase
            .table("plans")
            .select("id")
            .eq("code", payload.code)
            .limit(1)
            .execute()
        )

        if existing_response.data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Já existe um plano com este código.",
            )

        data = serialize_plan_payload(payload.model_dump())

        response = (
            supabase
            .table("plans")
            .insert(data)
            .execute()
        )

        if not response.data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Não foi possível criar plano.",
            )

        plan = response.data[0]

        write_audit_log(
            action="plan.create",
            entity_type="plan",
            entity_id=plan["id"],
            description=f"Plano criado: {plan.get('name')}",
            metadata={
                "plan": plan,
            },
            current_user=current_user,
            request=request,
        )

        return plan

    except HTTPException:
        raise
    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(error),
        )


@router.patch("/{plan_id}")
def update_plan(
    plan_id: str,
    payload: PlanUpdateRequest,
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    require_platform_admin(current_user)

    try:
        supabase = get_supabase_admin()

        old_response = (
            supabase
            .table("plans")
            .select("*")
            .eq("id", plan_id)
            .limit(1)
            .execute()
        )

        if not old_response.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Plano não encontrado.",
            )

        old_plan = old_response.data[0]

        update_data = serialize_plan_payload(payload.model_dump(exclude_unset=True))

        if "code" in update_data and update_data["code"] != old_plan.get("code"):
            existing_response = (
                supabase
                .table("plans")
                .select("id")
                .eq("code", update_data["code"])
                .neq("id", plan_id)
                .limit(1)
                .execute()
            )

            if existing_response.data:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Já existe outro plano com este código.",
                )

        update_data["updated_at"] = "now()"

        response = (
            supabase
            .table("plans")
            .update(update_data)
            .eq("id", plan_id)
            .execute()
        )

        if not response.data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Não foi possível atualizar plano.",
            )

        plan = response.data[0]

        write_audit_log(
            action="plan.update",
            entity_type="plan",
            entity_id=plan_id,
            description=f"Plano atualizado: {plan.get('name')}",
            metadata={
                "before": old_plan,
                "changes": update_data,
                "after": plan,
            },
            current_user=current_user,
            request=request,
        )

        return plan

    except HTTPException:
        raise
    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(error),
        )


@router.delete("/{plan_id}")
def disable_plan(
    plan_id: str,
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    require_platform_admin(current_user)

    try:
        supabase = get_supabase_admin()

        old_response = (
            supabase
            .table("plans")
            .select("*")
            .eq("id", plan_id)
            .limit(1)
            .execute()
        )

        if not old_response.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Plano não encontrado.",
            )

        old_plan = old_response.data[0]

        response = (
            supabase
            .table("plans")
            .update({
                "active": False,
                "updated_at": "now()",
            })
            .eq("id", plan_id)
            .execute()
        )

        if not response.data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Não foi possível desativar plano.",
            )

        plan = response.data[0]

        write_audit_log(
            action="plan.disable",
            entity_type="plan",
            entity_id=plan_id,
            description=f"Plano desativado: {old_plan.get('name')}",
            metadata={
                "before": old_plan,
                "after": plan,
            },
            current_user=current_user,
            request=request,
        )

        return plan

    except HTTPException:
        raise
    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(error),
        )