from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.stocks import (
    StocksSnapshotResponse,
    StocksWarehousePreferencesUpdateRequest,
    StocksWarehousePreferencesUpdateResponse,
    StocksWorkspaceResponse,
)
from app.services.company_config import resolve_company_config
from app.services.stock_warehouse_preferences import save_stock_warehouse_preferences
from app.services.stocks_snapshot import get_stocks_snapshot, get_stocks_workspace

router = APIRouter(prefix="/stocks", tags=["stocks"])


@router.get("/snapshot", response_model=StocksSnapshotResponse)
def stocks_snapshot(company: str | None = Query(default=None)):
    return StocksSnapshotResponse(**get_stocks_snapshot(company=company))


@router.get("/workspace", response_model=StocksWorkspaceResponse)
def stocks_workspace(
    company: str | None = Query(default=None),
    date_from: str | None = Query(default=None),
    date_to: str | None = Query(default=None),
    regional_order_min: int = Query(default=2, ge=0),
    minimum_supply: int = Query(default=5, ge=0),
    position_filter: str = Query(default="ALL"),
    assortment_filter: str = Query(default="ALL"),
    force_refresh: bool = Query(default=False),
    db: Session = Depends(get_db),
):
    return StocksWorkspaceResponse(
        **get_stocks_workspace(
            company=company,
            date_from=date_from,
            date_to=date_to,
            regional_order_min=regional_order_min,
            minimum_supply=minimum_supply,
            position_filter=position_filter,
            assortment_filter=assortment_filter,
            force_refresh=force_refresh,
            db=db,
        )
    )


@router.put("/warehouse-preferences", response_model=StocksWarehousePreferencesUpdateResponse)
def update_warehouse_preferences(
    payload: StocksWarehousePreferencesUpdateRequest,
    db: Session = Depends(get_db),
):
    company_name, config = resolve_company_config(payload.company)
    seller_client_id = (config.get("seller_client_id") or "").strip()
    preferences = save_stock_warehouse_preferences(
        db,
        company_name=company_name,
        seller_client_id=seller_client_id,
        city_keys=payload.city_keys,
    )
    return StocksWarehousePreferencesUpdateResponse(
        company=company_name,
        seller_client_id=seller_client_id,
        used_city_keys=sorted([city_key for city_key, is_used in preferences.items() if is_used]),
    )
