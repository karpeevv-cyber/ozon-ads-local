from fastapi import APIRouter

from app.api.auth import router as auth_router
from app.api.bids import router as bids_router
from app.api.campaigns import router as campaigns_router
from app.api.finance import router as finance_router
from app.api.health import router as health_router
from app.api.profile import router as profile_router
from app.api.stocks import router as stocks_router
from app.api.storage import router as storage_router
from app.api.trends import router as trends_router
from app.api.unit_economics import router as unit_economics_router


def build_api_router() -> APIRouter:
    router = APIRouter()
    router.include_router(auth_router)
    router.include_router(bids_router)
    router.include_router(health_router)
    router.include_router(profile_router)
    router.include_router(campaigns_router)
    router.include_router(finance_router)
    router.include_router(stocks_router)
    router.include_router(storage_router)
    router.include_router(trends_router)
    router.include_router(unit_economics_router)
    return router
