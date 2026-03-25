from __future__ import annotations

from app.services.company_config import resolve_company_config
from app.services.bid_history import apply_bid_and_log
from app.services.integrations.ozon_ads import (
    get_campaign_products_all,
    perf_token,
    update_campaign_product_bids,
)
from app.services.storage_paths import backend_data_path

def apply_bid_command(
    *,
    company: str | None,
    campaign_id: str,
    sku: str,
    bid_rub: float,
    reason: str,
    comment: str = "",
):
    company_name, config = resolve_company_config(company)
    perf_client_id = (config.get("perf_client_id") or "").strip() or None
    perf_client_secret = (config.get("perf_client_secret") or "").strip() or None
    token = perf_token(client_id=perf_client_id, client_secret=perf_client_secret)

    result = apply_bid_and_log(
        token=token,
        campaign_id=str(campaign_id),
        sku=str(sku),
        bid_rub=float(bid_rub),
        reason=str(reason),
        comment=str(comment),
        products_loader=get_campaign_products_all,
        bid_updater=update_campaign_product_bids,
        log_path=str(backend_data_path("bid_changes.csv")),
    )

    return {
        "company": company_name,
        "campaign_id": str(campaign_id),
        "sku": str(sku),
        "old_bid_micro": result.old_bid_micro,
        "new_bid_micro": result.new_bid_micro,
        "reason": result.reason,
        "comment": str(comment),
    }
