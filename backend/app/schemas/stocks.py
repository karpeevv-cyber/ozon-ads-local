from pydantic import BaseModel, Field


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


class StocksWorkspaceTimingResponse(BaseModel):
    resolve_company_ms: float = 0
    stocks_cache_ms: float = 0
    shipment_pairs_ms: float = 0
    shipment_rebuild_ms: float = 0
    dataframe_ms: float = 0
    shipment_events_ms: float = 0
    matrix_ms: float = 0
    total_ms: float = 0


class StocksWorkspaceCellResponse(BaseModel):
    class ShipmentEventItem(BaseModel):
        quantity: int
        event_at: str | None
        unsold_qty: int = 0
        free_storage_until: str | None = None
        paid_qty: int = 0

    city: str
    stock: int
    need60: int
    in_transit: int
    total_with_transit: int
    turnover_grade: str
    is_candidate: bool
    display_value: str
    shipment_total_qty: int = 0
    shipment_events_count: int = 0
    shipment_last_at: str | None = None
    paid_storage_qty: int = 0
    paid_storage_soon_30_qty: int = 0
    paid_storage_soon_60_qty: int = 0
    shipment_events: list[ShipmentEventItem] = Field(default_factory=list)


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
    timings: StocksWorkspaceTimingResponse = Field(default_factory=StocksWorkspaceTimingResponse)
    columns: list[str]
    rows: list[StocksWorkspaceRowResponse]
