from __future__ import annotations

from app.db.base import Base
from app.db.session import engine
from app.models import (
    BidChange,
    Campaign,
    CampaignComment,
    CampaignDailyMetric,
    CampaignProduct,
    MarketplaceCredential,
    Organization,
    StorageSnapshotCache,
    TrendsSnapshotCache,
    UnitEconomicsOverride,
)


def create_all() -> None:
    Base.metadata.create_all(bind=engine)
