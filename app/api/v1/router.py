from fastapi import APIRouter

from app.core.config import settings

from app.api.v1.health import router as health_router
from app.api.v1.auth_supabase import router as auth_router

from app.api.v1.tenants_supabase import router as tenants_router
from app.api.v1.categories_supabase import router as categories_router
from app.api.v1.products_supabase import router as products_router
from app.api.v1.stock_supabase import router as stock_router
from app.api.v1.sales_supabase import router as sales_router
from app.api.v1.billing_supabase import router as billing_router
from app.api.v1.subscriptions_supabase import router as subscriptions_router
from app.api.v1.coupons_supabase import router as coupons_router
from app.api.v1.dashboard_supabase import router as dashboard_router
from app.api.v1.admin_supabase import router as admin_router
from app.api.v1.audit_supabase import router as audit_router

api_router = APIRouter()

api_router.include_router(health_router)
api_router.include_router(auth_router)

api_router.include_router(tenants_router)
api_router.include_router(categories_router)
api_router.include_router(products_router)
api_router.include_router(stock_router)
api_router.include_router(sales_router)
api_router.include_router(billing_router)
api_router.include_router(subscriptions_router)
api_router.include_router(coupons_router)
api_router.include_router(dashboard_router)
api_router.include_router(admin_router)
api_router.include_router(audit_router)

if settings.APP_ENV == "local":
    from app.api.v1.supabase_test import router as supabase_test_router
    from app.api.v1.supabase_auth_test import router as supabase_auth_test_router

    api_router.include_router(supabase_test_router)
    api_router.include_router(supabase_auth_test_router)