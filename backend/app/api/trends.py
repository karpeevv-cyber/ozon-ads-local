from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.trends import TrendsSnapshotResponse
from app.services.trends_snapshot import get_trends_snapshot


router = APIRouter(prefix="/trends", tags=["trends"])


@router.get("/snapshot", response_model=TrendsSnapshotResponse)
def trends_snapshot(
    company: str | None = Query(default=None),
    date_from: str = Query(...),
    date_to: str = Query(...),
    horizon: str = Query(default="1-3 months"),
    search_filter: str = Query(default=""),
    refresh: bool = Query(default=False),
    db: Session = Depends(get_db),
):
    return TrendsSnapshotResponse(
        **get_trends_snapshot(
            company=company,
            date_from=date_from,
            date_to=date_to,
            horizon=horizon,
            search_filter=search_filter,
            refresh=refresh,
            db=db,
        )
    )
