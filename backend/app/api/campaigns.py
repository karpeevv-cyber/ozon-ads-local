from fastapi import APIRouter, Query

from app.schemas.campaigns import (
    CampaignReportResponse,
    CampaignSummaryResponse,
    CompanyConfigResponse,
)
from app.services.campaign_reporting import (
    build_report_rows,
    fetch_ads_stats_by_campaign_from_credentials,
    load_products_parallel,
)
from app.services.company_config import default_company_from_env, load_company_configs, resolve_company_config
from app.services.integrations.ozon_ads import get_running_campaigns
from app.services.integrations.ozon_ads import perf_token
from app.services.integrations.ozon_seller import seller_analytics_sku_day

router = APIRouter(prefix="/campaigns", tags=["campaigns"])


@router.get("/companies", response_model=list[CompanyConfigResponse])
def list_companies() -> list[CompanyConfigResponse]:
    configs = load_company_configs()
    if not configs:
        return [CompanyConfigResponse(name="default", **default_company_from_env())]
    return [CompanyConfigResponse(name=name, **data) for name, data in sorted(configs.items())]


@router.get("/running", response_model=list[CampaignSummaryResponse])
def list_running_campaigns(company: str | None = Query(default=None)) -> list[CampaignSummaryResponse]:
    _company_name, config = resolve_company_config(company)
    campaigns = get_running_campaigns(
        client_id=(config.get("perf_client_id") or "").strip() or None,
        client_secret=(config.get("perf_client_secret") or "").strip() or None,
    )
    return [
        CampaignSummaryResponse(
            id=str(campaign.get("id", "")),
            title=str(campaign.get("title", "") or ""),
            state=str(campaign.get("state", "") or ""),
        )
        for campaign in campaigns
    ]


@router.get("/report", response_model=CampaignReportResponse)
def get_campaign_report(
    company: str | None = Query(default=None),
    date_from: str = Query(...),
    date_to: str = Query(...),
    target_drr_pct: float = Query(default=20.0),
) -> CampaignReportResponse:
    company_name, config = resolve_company_config(company)
    perf_client_id = (config.get("perf_client_id") or "").strip() or None
    perf_client_secret = (config.get("perf_client_secret") or "").strip() or None
    seller_client_id = (config.get("seller_client_id") or "").strip() or None
    seller_api_key = (config.get("seller_api_key") or "").strip() or None

    running_campaigns = get_running_campaigns(
        client_id=perf_client_id,
        client_secret=perf_client_secret,
    )
    running_ids = [str(campaign.get("id")) for campaign in running_campaigns if campaign.get("id") is not None]

    if not running_ids:
        return CampaignReportResponse(
            company=company_name,
            date_from=date_from,
            date_to=date_to,
            target_drr_pct=float(target_drr_pct),
            running_campaigns_count=0,
            rows=[],
        )

    by_sku, _by_day, _by_day_sku = seller_analytics_sku_day(
        date_from,
        date_to,
        limit=1000,
        client_id=seller_client_id,
        api_key=seller_api_key,
    )
    stats_by_campaign_id = fetch_ads_stats_by_campaign_from_credentials(
        perf_client_id=perf_client_id,
        perf_client_secret=perf_client_secret,
        date_from=date_from,
        date_to=date_to,
        running_ids=running_ids,
        batch_size=15,
    )
    token = perf_token(client_id=perf_client_id, client_secret=perf_client_secret)
    products_by_campaign_id = load_products_parallel(token, running_ids, page_size=100)
    rows, _grand_total = build_report_rows(
        running_campaigns=running_campaigns,
        stats_by_campaign_id=stats_by_campaign_id,
        sales_map=by_sku,
        products_by_campaign_id=products_by_campaign_id,
    )

    return CampaignReportResponse(
        company=company_name,
        date_from=date_from,
        date_to=date_to,
        target_drr_pct=float(target_drr_pct),
        running_campaigns_count=len(running_ids),
        rows=rows,
    )
