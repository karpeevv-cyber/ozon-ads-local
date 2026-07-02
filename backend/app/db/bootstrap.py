from __future__ import annotations

from threading import Lock

from app.db.base import Base
from app.db.session import engine
from app.models import (
    BidChange,
    Campaign,
    CampaignComment,
    CampaignDailyMetric,
    CampaignProduct,
    MainOverviewCache,
    MarketplaceCredential,
    Organization,
    StockWarehousePreference,
    ShipmentEvent,
    ShipmentHistory,
    ShipmentTransit,
    StorageSnapshotCache,
    TrendsSnapshotCache,
    UnitEconomicsOverride,
)

_CREATE_ALL_LOCK = Lock()


def create_all() -> None:
    with _CREATE_ALL_LOCK:
        Base.metadata.create_all(bind=engine)
