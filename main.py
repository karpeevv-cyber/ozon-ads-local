from datetime import date, timedelta

from clients_ads import (
    perf_token,
    get_campaigns,
    get_campaign_products_all,
    get_campaign_stats_json,
)
from clients_seller import seller_total_sales_all
from report import chunks, build_report_rows, write_csv


def main():
    today = date.today()
    date_to = (today - timedelta(days=1)).isoformat()
    date_from = (today - timedelta(days=7)).isoformat()

    token = perf_token()

    campaigns = get_campaigns(token)
    running = [c for c in campaigns if c.get("state") == "CAMPAIGN_STATE_RUNNING"]
    if not running:
        print("No running campaigns.")
        return

    # Seller: один вызов за окно
    sales_map = seller_total_sales_all(date_from, date_to)

    # Ads stats батчами
    stats_by_campaign_id = {}
    running_ids = [str(c["id"]) for c in running]

    for batch in chunks(running_ids, 15):
        stats = get_campaign_stats_json(token, date_from, date_to, batch)
        rows = stats.get("rows", []) or []
        for r in rows:
            stats_by_campaign_id[str(r.get("id"))] = r

    # Products
    products_by_campaign_id = {}
    for c in running:
        cid = str(c["id"])
        products_by_campaign_id[cid] = get_campaign_products_all(token, cid, page_size=100)

    rows_csv, _ = build_report_rows(
        running_campaigns=running,
        stats_by_campaign_id=stats_by_campaign_id,
        sales_map=sales_map,
        products_by_campaign_id=products_by_campaign_id,
    )

    csv_path = f"report_{date_from}_to_{date_to}.csv"
    write_csv(rows_csv, csv_path)
    print(f"CSV saved: {csv_path}")


if __name__ == "__main__":
    main()
