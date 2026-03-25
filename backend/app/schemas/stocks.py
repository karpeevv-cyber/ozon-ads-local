from pydantic import BaseModel


class StockRowResponse(BaseModel):
    sku: str
    article: str
    title: str
    offer_id: str
    cluster: str
    turnover_grade: str
    available_stock_count: float
    ads_cluster: float
    transit_stock_count: float


class StocksSnapshotResponse(BaseModel):
    company: str
    seller_client_id: str
    sku_count: int
    rows: list[StockRowResponse]
