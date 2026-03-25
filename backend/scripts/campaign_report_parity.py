from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = REPO_ROOT / "backend"

sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(BACKEND_ROOT))

from app.services.campaign_reporting import build_report_rows as build_report_rows_new
from app.services.campaign_reporting import fetch_ads_stats_by_campaign_from_credentials
from app.services.campaign_reporting import load_products_parallel
from app.services.company_config import resolve_company_config
from app.services.integrations.ozon_ads import get_running_campaigns, perf_token
from app.services.integrations.ozon_seller import seller_analytics_sku_day
from report import build_report_rows as build_report_rows_legacy


def _row_key(row: dict) -> str:
    return str(row.get("campaign_id", ""))


def _normalize_rows(rows: list[dict]) -> dict[str, dict]:
    return {_row_key(row): row for row in rows}


def _build_shared_inputs(company: str | None, date_from: str, date_to: str):
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
    token = perf_token(client_id=perf_client_id, client_secret=perf_client_secret)
    stats_by_campaign_id = fetch_ads_stats_by_campaign_from_credentials(
        perf_client_id=perf_client_id,
        perf_client_secret=perf_client_secret,
        date_from=date_from,
        date_to=date_to,
        running_ids=running_ids,
        batch_size=15,
    )
    sales_map, _by_day, _by_day_sku = seller_analytics_sku_day(
        date_from,
        date_to,
        limit=1000,
        client_id=seller_client_id,
        api_key=seller_api_key,
    )
    products_by_campaign_id = load_products_parallel(token, running_ids, page_size=100)

    return {
        "company_name": company_name,
        "running_campaigns": running_campaigns,
        "stats_by_campaign_id": stats_by_campaign_id,
        "sales_map": sales_map,
        "products_by_campaign_id": products_by_campaign_id,
    }


def compare_reports(company: str | None, date_from: str, date_to: str) -> dict:
    shared = _build_shared_inputs(company, date_from, date_to)

    legacy_rows, legacy_grand_total = build_report_rows_legacy(
        running_campaigns=shared["running_campaigns"],
        stats_by_campaign_id=shared["stats_by_campaign_id"],
        sales_map=shared["sales_map"],
        products_by_campaign_id=shared["products_by_campaign_id"],
    )
    new_rows, new_grand_total = build_report_rows_new(
        running_campaigns=shared["running_campaigns"],
        stats_by_campaign_id=shared["stats_by_campaign_id"],
        sales_map=shared["sales_map"],
        products_by_campaign_id=shared["products_by_campaign_id"],
    )

    legacy_map = _normalize_rows(legacy_rows)
    new_map = _normalize_rows(new_rows)
    all_keys = sorted(set(legacy_map) | set(new_map))

    mismatches: list[dict] = []
    for key in all_keys:
        legacy_row = legacy_map.get(key)
        new_row = new_map.get(key)
        if legacy_row != new_row:
            mismatches.append(
                {
                    "campaign_id": key,
                    "legacy": legacy_row,
                    "new": new_row,
                }
            )

    return {
        "company": shared["company_name"],
        "date_from": date_from,
        "date_to": date_to,
        "running_campaigns_count": len(shared["running_campaigns"]),
        "legacy_rows_count": len(legacy_rows),
        "new_rows_count": len(new_rows),
        "grand_total_match": legacy_grand_total == new_grand_total,
        "rows_match": len(mismatches) == 0,
        "mismatch_count": len(mismatches),
        "mismatches": mismatches,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare legacy and new campaign report outputs.")
    parser.add_argument("--company", default=None, help="Company name from .env config")
    parser.add_argument("--date-from", required=True, dest="date_from", help="YYYY-MM-DD")
    parser.add_argument("--date-to", required=True, dest="date_to", help="YYYY-MM-DD")
    parser.add_argument("--json", action="store_true", help="Print full JSON result")
    args = parser.parse_args()

    result = compare_reports(args.company, args.date_from, args.date_to)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"company={result['company']}")
        print(f"period={result['date_from']}..{result['date_to']}")
        print(f"running_campaigns={result['running_campaigns_count']}")
        print(f"legacy_rows={result['legacy_rows_count']} new_rows={result['new_rows_count']}")
        print(f"grand_total_match={result['grand_total_match']}")
        print(f"rows_match={result['rows_match']}")
        print(f"mismatch_count={result['mismatch_count']}")
    return 0 if result["grand_total_match"] and result["rows_match"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
