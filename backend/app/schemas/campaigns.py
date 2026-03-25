from __future__ import annotations

from pydantic import BaseModel, Field


class CompanyConfigResponse(BaseModel):
    name: str
    perf_client_id: str = ""
    perf_client_secret: str = ""
    seller_client_id: str = ""
    seller_api_key: str = ""


class CampaignSummaryResponse(BaseModel):
    campaign_id: str = Field(alias="id")
    title: str = ""
    state: str = ""

    model_config = {"populate_by_name": True}


class CampaignReportRowResponse(BaseModel):
    campaign_id: str
    sku: str
    title: str
    money_spent: str
    views: str
    clicks: str
    click_price: str
    orders_money_ads: str
    total_revenue: str
    ordered_units: str
    total_drr_pct: str
    ctr: float
    cr: float
    vor: float
    vpo: float


class CampaignReportResponse(BaseModel):
    company: str
    date_from: str
    date_to: str
    target_drr_pct: float
    running_campaigns_count: int
    rows: list[CampaignReportRowResponse]
