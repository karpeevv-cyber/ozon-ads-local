from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta
import json

from app.services.integrations.ozon_ads import (
    get_campaign_products_all,
    get_campaign_stats_json,
    perf_token,
)


def parse_money(value) -> float:
    if value is None:
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace(" ", "").replace(",", ".")
    try:
        return float(text)
    except ValueError:
        return 0.0


def fmt_num(value):
    if value is None:
        return ""
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return str(int(round(value)))
    text = str(value).strip()
    if not text:
        return ""
    try:
        number = float(text.replace(" ", "").replace(",", "."))
        return str(int(round(number)))
    except Exception:
        return text


def fmt_float(value, digits: int = 1) -> str:
    try:
        return f"{float(value):.{digits}f}".rstrip("0").rstrip(".")
    except Exception:
        return ""


def chunks(items, size):
    for index in range(0, len(items), size):
        yield items[index : index + size]


def _micro_to_rub(value) -> str:
    try:
        if value is None:
            return ""
        text = str(value).strip()
        if not text or text.lower() in {"nan", "none", "<na>"}:
            return ""
        return fmt_float(float(text) / 1_000_000.0, 1)
    except Exception:
        return ""


def build_bid_change_map(bid_log_df, *, date_from: str, date_to: str) -> dict[tuple[str, str], str]:
    if bid_log_df is None or getattr(bid_log_df, "empty", True):
        return {}

    output: dict[tuple[str, str], list[str]] = {}
    try:
        rows = bid_log_df.copy()
        rows = rows[
            (rows["date"].astype(str) >= str(date_from))
            & (rows["date"].astype(str) <= str(date_to))
        ].copy()
        rows = rows.sort_values("ts_iso", ascending=False)
    except Exception:
        return {}

    for _, row in rows.iterrows():
        campaign_id = str(row.get("campaign_id", "") or "").strip()
        sku = str(row.get("sku", "") or "").strip()
        if not campaign_id or not sku:
            continue
        old_bid = _micro_to_rub(row.get("old_bid_micro"))
        new_bid = _micro_to_rub(row.get("new_bid_micro"))
        if not new_bid:
            continue
        if old_bid:
            line = f"{row.get('date', '')}: {old_bid} -> {new_bid}"
        else:
            line = f"{row.get('date', '')}: {new_bid}"
        reason = str(row.get("reason", "") or "").strip()
        comment = str(row.get("comment", "") or "").strip()
        if comment and not comment.startswith("__test_meta__:"):
            line = f"{line} / {comment}"
        elif reason:
            line = f"{line} / {reason}"
        output.setdefault((campaign_id, sku), []).append(line)
    return {key: "\n".join(value) for key, value in output.items()}


def build_active_test_map(bid_log_df, *, on_day: date | None = None) -> dict[tuple[str, str], bool]:
    if bid_log_df is None or getattr(bid_log_df, "empty", True):
        return {}

    day = (on_day or date.today()).isoformat()
    try:
        rows = bid_log_df[bid_log_df["reason"].astype(str) == "Test"].copy()
        rows = rows.sort_values("ts_iso", ascending=False)
    except Exception:
        return {}

    output: dict[tuple[str, str], bool] = {}
    for _, row in rows.iterrows():
        campaign_id = str(row.get("campaign_id", "") or "").strip()
        sku = str(row.get("sku", "") or "").strip()
        if not campaign_id or not sku or (campaign_id, sku) in output:
            continue
        comment = str(row.get("comment", "") or "").strip()
        if not comment.startswith("__test_meta__:"):
            continue
        try:
            payload = json.loads(comment[len("__test_meta__:") :])
        except Exception:
            continue
        date_from = str(payload.get("date_from", "") or "").strip()
        date_to = str(payload.get("date_to", "") or "").strip()
        if date_from <= day <= date_to:
            output[(campaign_id, sku)] = True
    return output


def build_campaign_comment_maps(
    comments_df,
    *,
    company_name: str,
    date_from: str,
    date_to: str,
) -> tuple[dict[str, str], str]:
    if comments_df is None or getattr(comments_df, "empty", True):
        return {}, ""

    try:
        comments = comments_df.copy()
        if "company" in comments.columns:
            comments = comments[comments["company"].astype(str).isin(["", str(company_name)])].copy()
        comments = comments[
            (comments["day"].astype(str) >= str(date_from))
            & (comments["day"].astype(str) <= str(date_to))
        ].copy()
        comments = comments.sort_values(["day", "ts"], ascending=[False, False])
    except Exception:
        return {}, ""

    comment_map: dict[str, list[str]] = {}
    all_comments: list[str] = []
    seen_all: set[str] = set()
    for _, row in comments.iterrows():
        text = str(row.get("comment", "") or "").strip()
        if not text:
            continue
        day_value = str(row.get("day", "") or "").strip()
        line = f"{day_value}: {text}" if day_value else text
        campaign_id = str(row.get("campaign_id", "") or "").strip()
        if campaign_id.lower() == "all":
            if line not in seen_all:
                seen_all.add(line)
                all_comments.append(line)
            continue
        comment_map.setdefault(campaign_id, [])
        if line not in comment_map[campaign_id]:
            comment_map[campaign_id].append(line)
    return {key: "\n".join(value) for key, value in comment_map.items()}, "\n".join(all_comments)


def daterange(date_from: date, date_to: date):
    current = date_from
    while current <= date_to:
        yield current
        current += timedelta(days=1)


def _to_num(value) -> float:
    if value is None:
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    try:
        text = str(value).strip().replace(" ", "").replace(",", ".")
        return float(text) if text else 0.0
    except Exception:
        return 0.0


def _to_int_round(value) -> int:
    try:
        return int(round(_to_num(value)))
    except Exception:
        return 0


def campaign_display_fields(campaign_title: str, items: list[dict]):
    skus = [str(item.get("sku")) for item in items if item.get("sku") is not None]

    if len(skus) == 0:
        return "-", campaign_title, None, skus

    if len(skus) == 1:
        one = items[0]
        out_sku = skus[0]
        out_title = one.get("title", "") or campaign_title
        bid_raw = one.get("bid")
        try:
            bid_value = int(bid_raw) / 1_000_000
        except Exception:
            bid_value = None
        return out_sku, out_title, bid_value, skus

    return "several", "several", None, skus


def load_products_parallel(token: str, campaign_ids: list[str], page_size: int = 100) -> dict[str, list[dict]]:
    if not campaign_ids:
        return {}

    output: dict[str, list[dict]] = {str(campaign_id): [] for campaign_id in campaign_ids}
    max_workers = min(4, max(1, len(campaign_ids)))

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_map = {
            executor.submit(get_campaign_products_all, token, str(campaign_id), page_size): str(campaign_id)
            for campaign_id in campaign_ids
        }
        for future in as_completed(future_map):
            campaign_id = future_map[future]
            output[campaign_id] = future.result()

    return output


def fetch_ads_stats_by_campaign(token: str, date_from: str, date_to: str, running_ids: list[str], batch_size: int):
    stats_by_campaign_id: dict[str, dict] = {}
    for batch in chunks(running_ids, int(batch_size)):
        stats = get_campaign_stats_json(token, date_from, date_to, batch)
        for row in stats.get("rows", []) or []:
            stats_by_campaign_id[str(row.get("id"))] = row
    return stats_by_campaign_id


def fetch_ads_stats_by_campaign_from_credentials(
    *,
    perf_client_id: str | None,
    perf_client_secret: str | None,
    date_from: str,
    date_to: str,
    running_ids: list[str],
    batch_size: int,
):
    token = perf_token(client_id=perf_client_id, client_secret=perf_client_secret)
    return fetch_ads_stats_by_campaign(token, date_from, date_to, running_ids, batch_size)


def fetch_ads_daily_totals(
    token: str,
    date_from: str,
    date_to: str,
    running_ids: list[str],
    batch_size: int,
    return_by_campaign: bool = False,
):
    start = datetime.fromisoformat(date_from).date()
    end = datetime.fromisoformat(date_to).date()
    days = [day.isoformat() for day in daterange(start, end)]

    totals = []
    by_campaign_day = {} if return_by_campaign else None
    for day_str in days:
        day_spend = 0.0
        day_views = 0
        day_clicks = 0
        day_orders_money = 0.0
        day_orders = 0

        for batch in chunks(running_ids, int(batch_size)):
            stats_day = get_campaign_stats_json(token, day_str, day_str, batch)
            for row in stats_day.get("rows", []) or []:
                spend = _to_num(row.get("moneySpent", 0))
                views = _to_int_round(row.get("views", 0))
                clicks = _to_int_round(row.get("clicks", 0))
                orders_money = _to_num(row.get("ordersMoney", 0))
                orders = _to_int_round(row.get("orders", 0))
                click_price_api = _to_num(row.get("clickPrice", 0))
                click_price = (spend / clicks) if clicks > 0 else click_price_api

                day_spend += spend
                day_views += views
                day_clicks += clicks
                day_orders_money += orders_money
                day_orders += orders

                if return_by_campaign:
                    campaign_id = str(row.get("id"))
                    by_campaign_day[(day_str, campaign_id)] = {
                        "money_spent": float(spend),
                        "views": views,
                        "clicks": clicks,
                        "click_price": float(click_price),
                        "orders_money_ads": float(orders_money),
                        "orders": orders,
                    }

        totals.append(
            {
                "day": day_str,
                "views": day_views,
                "clicks": day_clicks,
                "money_spent": float(day_spend),
                "orders_money_ads": float(day_orders_money),
                "orders": int(day_orders),
            }
        )
    if return_by_campaign:
        return totals, by_campaign_day
    return totals


def build_campaign_daily_rows(
    *,
    campaign_id: str,
    date_from: str,
    date_to: str,
    seller_by_day_sku: dict,
    ads_daily_by_campaign: dict,
    target_drr: float = 0.2,
    items: list[dict] | None = None,
):
    items = items or []
    out_sku, out_title, _out_bid, skus = campaign_display_fields("", items)
    start = datetime.fromisoformat(date_from).date()
    end = datetime.fromisoformat(date_to).date()

    output: list[dict] = []
    for day in daterange(start, end):
        day_str = day.isoformat()
        stats = ads_daily_by_campaign.get((day_str, str(campaign_id)), {})
        money_spent = float(stats.get("money_spent", 0.0) or 0.0)
        views = int(stats.get("views", 0) or 0)
        clicks = int(stats.get("clicks", 0) or 0)
        click_price = float(stats.get("click_price", 0.0) or 0.0)
        orders = int(stats.get("orders", 0) or 0)
        orders_money_ads = float(stats.get("orders_money_ads", 0.0) or 0.0)

        total_revenue = 0.0
        total_units = 0
        for sku in skus:
            revenue, units = seller_by_day_sku.get((day_str, str(sku)), (0.0, 0))
            total_revenue += float(revenue)
            total_units += int(units)

        total_drr_pct = (money_spent / total_revenue * 100.0) if total_revenue > 0 else 0.0
        ctr_pct = (clicks / views * 100.0) if views > 0 else 0.0
        cr_pct = (total_units / clicks * 100.0) if clicks > 0 else 0.0
        vor_pct = (total_units / views * 100.0) if views > 0 else 0.0
        cpm = (money_spent / views * 1000.0) if views > 0 else 0.0
        rpc = (total_revenue / clicks) if clicks > 0 else 0.0
        target_cpc = rpc * target_drr
        vpo = (views / total_units) if total_units > 0 else 0.0
        ipo = (views / total_units) if total_units > 0 else 0.0

        output.append(
            {
                "day": day_str,
                "campaign_id": str(campaign_id),
                "sku": out_sku,
                "title": out_title,
                "money_spent": money_spent,
                "views": views,
                "clicks": clicks,
                "click_price": click_price,
                "orders_money_ads": orders_money_ads,
                "cpm": round(cpm, 0),
                "total_revenue": total_revenue,
                "ordered_units": total_units,
                "total_drr_pct": round(total_drr_pct, 1),
                "ctr": round(ctr_pct, 1),
                "cr": round(cr_pct, 1),
                "vor": round(vor_pct, 1),
                "rpc": round(rpc, 1),
                "target_cpc": round(target_cpc, 1),
                "vpo": round(vpo, 1),
                "ipo": round(ipo, 0),
                "orders": orders,
            }
        )

    return output


def compute_daily_breakdown(ads_daily_rows: list[dict], seller_by_day: dict, target_drr: float = 0.2):
    output = []
    for row in ads_daily_rows:
        day = row["day"]
        views = int(row.get("views", 0) or 0)
        clicks = int(row.get("clicks", 0) or 0)
        spend = float(row.get("money_spent", 0.0) or 0.0)
        orders_money_ads = float(row.get("orders_money_ads", 0.0) or 0.0)

        revenue, units = seller_by_day.get(day, (0.0, 0))
        drr = (spend / revenue * 100.0) if revenue > 0 else 0.0
        cpm = (spend / views * 1000.0) if views > 0 else 0.0
        ctr = (clicks / views * 100.0) if views > 0 else 0.0
        cr = (units / clicks * 100.0) if clicks > 0 else 0.0
        vor = (units / views * 100.0) if views > 0 else 0.0
        rpc = (revenue / clicks) if clicks > 0 else 0.0
        target_cpc = rpc * target_drr
        vpo = (views / units) if units > 0 else 0.0
        ads_share = (orders_money_ads / revenue * 100.0) if revenue > 0 else 0.0
        organic_pct = (100.0 - ads_share) if revenue > 0 else 0.0
        organic_pct = max(0.0, min(100.0, organic_pct))

        output.append(
            {
                "day": day,
                "views": views,
                "clicks": clicks,
                "money_spent": spend,
                "orders_money_ads": orders_money_ads,
                "total_revenue": float(revenue),
                "ordered_units": int(units),
                "total_drr_pct": round(drr, 1),
                "cpm": round(cpm, 0),
                "ctr": round(ctr, 1),
                "cr": round(cr, 1),
                "vor": round(vor, 1),
                "rpc": round(rpc, 1),
                "target_cpc": round(target_cpc, 1),
                "vpo": round(vpo, 1),
                "organic_pct": round(organic_pct, 1),
            }
        )
    return output


def build_report_rows(
    *,
    running_campaigns: list[dict],
    stats_by_campaign_id: dict,
    sales_map: dict,
    products_by_campaign_id: dict,
    target_drr: float = 0.2,
    bid_change_map: dict[tuple[str, str], str] | None = None,
    active_test_map: dict[tuple[str, str], bool] | None = None,
    comment_map: dict[str, str] | None = None,
    comment_all: str = "",
):
    bid_change_map = bid_change_map or {}
    active_test_map = active_test_map or {}
    comment_map = comment_map or {}
    rows = []
    gt_money_spent = 0.0
    gt_views = 0
    gt_clicks = 0
    gt_to_cart = 0
    gt_orders = 0
    gt_orders_money = 0.0
    gt_revenue = 0.0
    gt_units = 0

    for campaign in running_campaigns:
        campaign_id = str(campaign["id"])
        campaign_title = campaign.get("title", "")
        items = products_by_campaign_id.get(campaign_id, [])
        out_sku, out_title, out_bid, skus = campaign_display_fields(campaign_title, items)
        stats_row = stats_by_campaign_id.get(campaign_id, {})

        money_spent = parse_money(stats_row.get("moneySpent"))
        views = int(parse_money(stats_row.get("views")))
        clicks = int(parse_money(stats_row.get("clicks")))
        click_price = parse_money(stats_row.get("clickPrice"))
        to_cart = int(parse_money(stats_row.get("toCart")))
        orders = int(parse_money(stats_row.get("orders")))
        orders_money = parse_money(stats_row.get("ordersMoney"))

        total_revenue = 0.0
        total_units = 0
        for sku in skus:
            revenue, units = sales_map.get(sku, (0.0, 0))
            total_revenue += revenue
            total_units += units

        ctr_pct = (clicks / views * 100.0) if views > 0 else 0.0
        cr_pct = (total_units / clicks * 100.0) if clicks > 0 else 0.0
        vor_pct = (total_units / views * 100.0) if views > 0 else 0.0
        cpm = (money_spent / views * 1000.0) if views > 0 else 0.0
        rpc = (total_revenue / clicks) if clicks > 0 else 0.0
        target_cpc = rpc * float(target_drr)
        vpo = (views / total_units) if total_units > 0 else 0.0
        ipo = (views / total_units) if total_units > 0 else 0.0
        total_drr_pct = (money_spent / total_revenue * 100.0) if total_revenue > 0 else 0.0

        article_values: list[str] = []
        for item in items or []:
            article = str(item.get("offer_id") or item.get("offerId") or "").strip()
            if article:
                article_values.append(article)
        article_values = list(dict.fromkeys(article_values))
        if not article_values:
            article = ""
        elif len(article_values) == 1:
            article = article_values[0]
        else:
            article = "several"

        single_sku = out_sku if len(skus) == 1 else ""

        gt_money_spent += money_spent
        gt_views += views
        gt_clicks += clicks
        gt_to_cart += to_cart
        gt_orders += orders
        gt_orders_money += orders_money
        gt_revenue += total_revenue
        gt_units += total_units

        rows.append(
            {
                "campaign_id": campaign_id,
                "sku": out_sku,
                "article": article,
                "title": out_title,
                "money_spent": fmt_num(money_spent),
                "views": fmt_num(views),
                "clicks": fmt_num(clicks),
                "click_price": fmt_num(click_price),
                "cpm": fmt_num(cpm),
                "orders_money_ads": fmt_num(orders_money),
                "total_revenue": fmt_num(total_revenue),
                "ordered_units": fmt_num(total_units),
                "total_drr_pct": fmt_num(round(total_drr_pct, 2)),
                "ctr": round(ctr_pct, 1),
                "cr": round(cr_pct, 1),
                "vor": round(vor_pct, 1),
                "rpc": round(rpc, 1),
                "target_cpc": round(target_cpc, 1),
                "vpo": round(vpo, 1),
                "ipo": round(ipo, 0),
                "bid": fmt_float(out_bid, 1) if out_bid is not None and len(skus) == 1 else "",
                "bid_change": bid_change_map.get((campaign_id, single_sku), ""),
                "test": "Да" if active_test_map.get((campaign_id, single_sku)) else "",
                "comment": comment_map.get(campaign_id, ""),
                "comment_all": comment_all,
            }
        )

    gt_click_price = (gt_money_spent / gt_clicks) if gt_clicks > 0 else 0.0
    gt_drr_pct = (gt_money_spent / gt_revenue * 100.0) if gt_revenue > 0 else 0.0
    gt_ctr = (gt_clicks / gt_views * 100.0) if gt_views > 0 else 0.0
    gt_cr = (gt_units / gt_clicks * 100.0) if gt_clicks > 0 else 0.0
    gt_vor = (gt_units / gt_views * 100.0) if gt_views > 0 else 0.0
    gt_vpo = (gt_views / gt_units) if gt_units > 0 else 0.0
    gt_cpm = (gt_money_spent / gt_views * 1000.0) if gt_views > 0 else 0.0
    gt_rpc = (gt_revenue / gt_clicks) if gt_clicks > 0 else 0.0
    gt_target_cpc = gt_rpc * float(target_drr)
    gt_ipo = (gt_views / gt_units) if gt_units > 0 else 0.0

    grand_total = {
        "campaign_id": "GRAND_TOTAL",
        "sku": "",
        "article": "",
        "title": "",
        "money_spent": fmt_num(gt_money_spent),
        "views": fmt_num(gt_views),
        "clicks": fmt_num(gt_clicks),
        "click_price": fmt_num(round(gt_click_price, 2)),
        "cpm": fmt_num(gt_cpm),
        "orders_money_ads": fmt_num(gt_orders_money),
        "total_revenue": fmt_num(gt_revenue),
        "ordered_units": fmt_num(gt_units),
        "total_drr_pct": fmt_num(round(gt_drr_pct, 2)),
        "ctr": round(gt_ctr, 1),
        "cr": round(gt_cr, 1),
        "vor": round(gt_vor, 1),
        "rpc": round(gt_rpc, 1),
        "target_cpc": round(gt_target_cpc, 1),
        "vpo": round(gt_vpo, 1),
        "ipo": round(gt_ipo, 0),
        "bid": "",
        "bid_change": "",
        "test": "",
        "comment": "",
        "comment_all": comment_all,
    }
    rows.append(grand_total)
    return rows, grand_total
