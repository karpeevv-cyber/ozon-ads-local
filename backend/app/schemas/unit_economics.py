from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class UnitEconomicsDayRow(BaseModel):
    day: str
    revenue: float
    ebitda_total: float
    tea_cost: float
    package_cost: float
    label_cost: float
    packing_cost: float
    delivery_fbo: float
    promotion: float
    ozon_percent_cost: float
    ozon_logistics: float
    other_costs: float
    review_points: float
    seller_bonuses: float
    taxes: float
    units_sold: float


class UnitEconomicsSummaryResponse(BaseModel):
    company: str
    date_from: str
    date_to: str
    rows: list[UnitEconomicsDayRow]
    totals: dict[str, float]
    totals_pct: dict[str, Any]


class UnitEconomicsProductRow(BaseModel):
    sku: str
    name: str
    tea_cost: float
    package_cost: float
    label_cost: float
    packing_cost: float


class UnitEconomicsProductsResponse(BaseModel):
    company: str
    date_from: str
    date_to: str
    rows: list[UnitEconomicsProductRow]


class UnitEconomicsProductUpdateRow(BaseModel):
    sku: str
    position: str
    tea_cost: float
    package_cost: float
    label_cost: float
    packing_cost: float


class UnitEconomicsProductsUpdateRequest(BaseModel):
    company: str | None = None
    rows: list[UnitEconomicsProductUpdateRow]


class UnitEconomicsProductsUpdateResponse(BaseModel):
    company: str
    rows: list[UnitEconomicsProductRow]
    saved_count: int
