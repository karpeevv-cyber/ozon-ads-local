from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.api.deps import get_admin_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.unit_economics import (
    UnitEconomicsProductsResponse,
    UnitEconomicsProductsUpdateRequest,
    UnitEconomicsProductsUpdateResponse,
    UnitEconomicsSummaryResponse,
)
from sqlalchemy.orm import Session
from app.services.unit_economics import (
    get_unit_economics_products,
    get_unit_economics_summary,
    update_unit_economics_products,
)


router = APIRouter(prefix="/unit-economics", tags=["unit-economics"])


@router.get("/summary", response_model=UnitEconomicsSummaryResponse)
def unit_economics_summary(
    company: str | None = Query(default=None),
    date_from: str = Query(...),
    date_to: str = Query(...),
    db: Session = Depends(get_db),
):
    return UnitEconomicsSummaryResponse(
        **get_unit_economics_summary(company=company, date_from=date_from, date_to=date_to, db=db)
    )


@router.get("/products", response_model=UnitEconomicsProductsResponse)
def unit_economics_products(
    company: str | None = Query(default=None),
    date_from: str = Query(...),
    date_to: str = Query(...),
    db: Session = Depends(get_db),
):
    return UnitEconomicsProductsResponse(
        **get_unit_economics_products(company=company, date_from=date_from, date_to=date_to, db=db)
    )


@router.put("/products", response_model=UnitEconomicsProductsUpdateResponse)
def unit_economics_products_update(
    payload: UnitEconomicsProductsUpdateRequest,
    _current_user: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    return UnitEconomicsProductsUpdateResponse(
        **update_unit_economics_products(
            company=payload.company,
            rows=[row.model_dump() for row in payload.rows],
            db=db,
        )
    )
