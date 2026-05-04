from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.stocks import StocksSnapshotResponse, StocksWorkspaceResponse
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
    regional_order_target: int = Query(default=5, ge=0),
    position_filter: str = Query(default="ALL"),
    force_refresh: bool = Query(default=False),
    db: Session = Depends(get_db),
):
    return StocksWorkspaceResponse(
        **get_stocks_workspace(
            company=company,
            date_from=date_from,
            date_to=date_to,
            regional_order_min=regional_order_min,
            regional_order_target=regional_order_target,
            position_filter=position_filter,
            force_refresh=force_refresh,
            db=db,
        )
    )
