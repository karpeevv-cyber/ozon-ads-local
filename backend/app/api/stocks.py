from fastapi import APIRouter, Query

from app.schemas.stocks import StocksSnapshotResponse
from app.services.stocks_snapshot import get_stocks_snapshot

router = APIRouter(prefix="/stocks", tags=["stocks"])


@router.get("/snapshot", response_model=StocksSnapshotResponse)
def stocks_snapshot(company: str | None = Query(default=None)):
    return StocksSnapshotResponse(**get_stocks_snapshot(company=company))
