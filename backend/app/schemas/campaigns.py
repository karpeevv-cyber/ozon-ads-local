from __future__ import annotations

from pydantic import BaseModel, Field


class CompanyConfigResponse(BaseModel):
    name: str
    display_name: str | None = None


class CampaignSummaryResponse(BaseModel):
    campaign_id: str = Field(alias="id")
    title: str = ""
    state: str = ""

    model_config = {"populate_by_name": True}


class CampaignReportRowResponse(BaseModel):
    campaign_id: str
    sku: str
    article: str = ""
    title: str
    money_spent: str
    views: str
    clicks: str
    click_price: str
    cpm: str = ""
    orders_money_ads: str
    total_revenue: str
    ordered_units: str
    total_drr_pct: str
    ctr: float
    cr: float
    vor: float
    rpc: float = 0.0
    target_cpc: float = 0.0
    vpo: float
    ipo: float = 0.0
    bid: str = ""
    bid_change: str = ""
    test: str = ""
    comment: str = ""
    comment_all: str = ""


class CampaignReportResponse(BaseModel):
    company: str
    date_from: str
    date_to: str
    target_drr_pct: float
    running_campaigns_count: int
    rows: list[CampaignReportRowResponse]


class MainOverviewChartRowResponse(BaseModel):
    day: str
    total_revenue: float
    money_spent: float
    total_drr_pct: float


class MainOverviewDailyRowResponse(BaseModel):
    day: str
    total_revenue: float
    total_drr_pct: float
    money_spent: float
    views: float
    clicks: float
    ordered_units: float
    ctr: float
    cr: float
    organic_pct: float
    bid_changes_cnt: int
    comment: str = ""


class MainOverviewWeeklyRowResponse(BaseModel):
    week: str
    total_revenue: float
    total_drr_pct: float
    ebitda: float
    ebitda_pct: float
    total_revenue_per_day: float
    money_spent_per_day: float
    views_per_day: float
    clicks_per_day: float
    ordered_units_per_day: float
    ctr: float
    cr: float
    organic_pct: float
    bid_changes_cnt: int
    comment: str = ""


class MainOverviewResponse(BaseModel):
    company: str
    date_from: str
    date_to: str
    target_drr_pct: float
    cache_hit: bool = False
    cached_at: str | None = None
    chart_rows: list[MainOverviewChartRowResponse]
    daily_rows: list[MainOverviewDailyRowResponse]
    weekly_rows: list[MainOverviewWeeklyRowResponse]
