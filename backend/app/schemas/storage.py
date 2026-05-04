from pydantic import BaseModel


class StorageRiskRowResponse(BaseModel):
    city: str
    article: str
    fee_from_date: str
    days_until_fee_start: int
    sales_per_day: float
    qty_remaining_now: int
    qty_expected_at_fee_start: int
    volume_expected_liters: float
    estimated_daily_fee_rub: float


class StorageSnapshotResponse(BaseModel):
    company: str
    seller_client_id: str
    cache_updated_at: str | None = None
    cache_source: str = ""
    sku_count: int
    order_count: int
    ship_lot_count: int
    stock_articles_count: int
    lot_rows: list[dict]
    risk_rows: list[StorageRiskRowResponse]
    unknown_stock_rows: list[dict]
