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


class StocksWorkspaceSettingsResponse(BaseModel):
    regional_order_min: int
    regional_order_target: int
    position_filter: str


class StocksWorkspaceSummaryResponse(BaseModel):
    article_count: int
    city_count: int
    candidate_count: int
    approved_count: int


class StocksWorkspaceCellResponse(BaseModel):
    city: str
    stock: int
    need60: int
    in_transit: int
    total_with_transit: int
    turnover_grade: str
    is_candidate: bool
    display_value: str


class StocksWorkspaceRowResponse(BaseModel):
    article: str
    title: str
    cells: list[StocksWorkspaceCellResponse]


class StocksWorkspaceResponse(BaseModel):
    company: str
    seller_client_id: str
    sku_count: int
    stocks_updated_at: str | None
    shipments_updated_at: str | None
    settings: StocksWorkspaceSettingsResponse
    summary: StocksWorkspaceSummaryResponse
    columns: list[str]
    rows: list[StocksWorkspaceRowResponse]
