from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.storage import StorageSnapshotResponse
from app.services.storage_snapshot import get_storage_snapshot

router = APIRouter(prefix="/storage", tags=["storage"])


@router.get("/snapshot", response_model=StorageSnapshotResponse)
def storage_snapshot(
    company: str | None = Query(default=None),
    force_refresh: bool = Query(default=False),
    db: Session = Depends(get_db),
):
    return StorageSnapshotResponse(**get_storage_snapshot(company=company, force_refresh=force_refresh, db=db))
