from __future__ import annotations

import json
from datetime import date, timedelta

import pandas as pd

from app.services.bid_log import load_bid_changes_df, load_campaign_comments_df
from app.services.campaign_reporting import (
    build_campaign_daily_rows,
    campaign_display_fields,
    fetch_ads_daily_totals,
    load_products_parallel,
)
from app.services.company_config import resolve_company_config
from app.services.integrations.ozon_ads import get_campaign_products_all, get_running_campaigns, perf_token
from app.services.integrations.ozon_seller import seller_analytics_sku_day, seller_analytics_stocks
from app.services.main_overview import _campaign_weekly_aggregate

TEST_META_PREFIX = "__test_meta__:"


def _num(value) -> float:
    try:
        if value is None:
            return 0.0
        if isinstance(value, (int, float)):
            return float(value)
        text = str(value).strip().replace(" ", "").replace(",", ".")
        return float(text) if text else 0.0
    except Exception:
        return 0.0


def _round_row(row: dict) -> dict:
    rounded = dict(row)
    for key in [
        "money_spent",
        "click_price",
        "orders_money_ads",
        "cpm",
        "total_revenue",
        "total_drr_pct",
        "ctr",
        "cr",
        "target_cpc",
    ]:
        if key in rounded:
            rounded[key] = round(_num(rounded[key]), 1)
    for key in ["views", "clicks", "ordered_units", "orders", "ipo", "days_in_period"]:
        if key in rounded:
            rounded[key] = int(round(_num(rounded[key])))
    return rounded


def _current_bid_rub(items: list[dict], sku: str) -> float | None:
    for item in items or []:
        if str(item.get("sku")) != str(sku):
            continue
        raw = item.get("bid")
        if raw is None:
            raw = item.get("current_bid") or item.get("currentBid")
        try:
            return int(float(str(raw).strip().replace(" ", "").replace(",", "."))) / 1_000_000
        except Exception:
            return None
    return None


def _sku_offer_map(*, skus: list[str], seller_client_id: str | None, seller_api_key: str | None) -> dict[str, str]:
    sku_values = [str(sku).strip() for sku in skus if str(sku).strip().isdigit()]
    if not sku_values:
        return {}
    out: dict[str, str] = {}
    for index in range(0, len(sku_values), 200):
        response = seller_analytics_stocks(
            skus=sku_values[index : index + 200],
            client_id=seller_client_id,
            api_key=seller_api_key,
        )
        for item in response.get("items", []) or []:
            sku = item.get("sku")
            if sku is not None:
                out[str(sku)] = str(item.get("offer_id") or "").strip()
    return out


def _build_bid_change_maps(bid_log_df, *, campaign_id: str, sku: str, date_from: str, date_to: str):
    day_map: dict[str, str] = {}
    week_map: dict[str, str] = {}
    if bid_log_df is None or getattr(bid_log_df, "empty", True) or not sku:
        return day_map, week_map
    rows = bid_log_df.copy()
    rows = rows[
        (rows["campaign_id"].astype(str) == str(campaign_id))
        & (rows["sku"].astype(str) == str(sku))
        & (rows["date"].astype(str) >= str(date_from))
        & (rows["date"].astype(str) <= str(date_to))
    ].copy()
    if rows.empty:
        return day_map, week_map
    rows = rows.sort_values("ts_iso", ascending=False)
    for _, row in rows.iterrows():
        day = str(row.get("date", "") or "")
        old_bid = _num(row.get("old_bid_micro")) / 1_000_000 if str(row.get("old_bid_micro", "")).strip() else None
        new_bid = _num(row.get("new_bid_micro")) / 1_000_000 if str(row.get("new_bid_micro", "")).strip() else None
        if new_bid is None:
            continue
        if old_bid is None:
            line = f"{day}: {new_bid:g}"
        else:
            line = f"{day}: {old_bid:g} -> {new_bid:g}"
        comment = str(row.get("comment", "") or "").strip()
        if comment and not comment.startswith(TEST_META_PREFIX):
            line = f"{line} / {comment}"
        day_map.setdefault(day, [])
        day_map[day].append(line)
        try:
            week = (date.fromisoformat(day) - timedelta(days=date.fromisoformat(day).weekday())).isoformat()
            week_map.setdefault(week, [])
            week_map[week].append(line)
        except Exception:
            pass
    return {k: "\n".join(v) for k, v in day_map.items()}, {k: "\n".join(v) for k, v in week_map.items()}


def _build_comment_maps(comments_df, *, company_name: str, campaign_id: str):
    day_map: dict[str, str] = {}
    week_map: dict[str, str] = {}
    all_day_map: dict[str, str] = {}
    all_week_map: dict[str, str] = {}
    recent: list[dict] = []
    if comments_df is None or getattr(comments_df, "empty", True):
        return day_map, week_map, all_day_map, all_week_map, recent
    rows = comments_df.copy()
    if "company" in rows.columns:
        rows = rows[rows["company"].astype(str).isin(["", str(company_name)])].copy()
    recent_rows = rows[rows["campaign_id"].astype(str).isin([str(campaign_id), "all"])].copy()
    recent_rows = recent_rows.sort_values(["day", "ts"], ascending=[False, False]).head(10)
    recent = [
        {"day": str(row.get("day", "") or ""), "ts": str(row.get("ts", "") or ""), "comment": str(row.get("comment", "") or "")}
        for _, row in recent_rows.iterrows()
    ]

    def build(rows_part):
        day_out: dict[str, list[str]] = {}
        week_out: dict[str, list[str]] = {}
        for _, row in rows_part.sort_values(["day", "ts"], ascending=[False, False]).iterrows():
            text = str(row.get("comment", "") or "").strip()
            day = str(row.get("day", "") or "").strip()
            week = str(row.get("week", "") or "").strip()
            if not text:
                continue
            day_out.setdefault(day, [])
            if text not in day_out[day]:
                day_out[day].append(text)
            week_out.setdefault(week, [])
            line = f"{day}: {text}" if day else text
            if line not in week_out[week]:
                week_out[week].append(line)
        return {k: "\n".join(v) for k, v in day_out.items()}, {k: "\n".join(v) for k, v in week_out.items()}

    day_map, week_map = build(rows[rows["campaign_id"].astype(str) == str(campaign_id)].copy())
    all_day_map, all_week_map = build(rows[rows["campaign_id"].astype(str).str.lower() == "all"].copy())
    return day_map, week_map, all_day_map, all_week_map, recent


def _parse_test_comment(comment: str) -> dict | None:
    text = str(comment or "").strip()
    if not text.startswith(TEST_META_PREFIX):
        return None
    try:
        raw = json.loads(text[len(TEST_META_PREFIX) :])
    except Exception:
        return None
    try:
        target_clicks = int(float(str(raw.get("target_clicks", 0)).replace(",", ".")))
    except Exception:
        target_clicks = 0
    return {
        "start_date": str(raw.get("start_date", raw.get("date_from", "")) or ""),
        "target_clicks": target_clicks,
        "essence": str(raw.get("essence", "") or ""),
        "expectations": str(raw.get("expectations", "") or ""),
        "note": str(raw.get("note", "") or ""),
        "company": str(raw.get("company", "") or ""),
    }


def _test_history(bid_log_df, *, campaign_id: str, sku: str, company_name: str) -> list[dict]:
    if bid_log_df is None or getattr(bid_log_df, "empty", True) or not sku:
        return []
    rows = bid_log_df[
        (bid_log_df["campaign_id"].astype(str) == str(campaign_id))
        & (bid_log_df["sku"].astype(str) == str(sku))
        & (bid_log_df["reason"].astype(str) == "Test")
    ].copy()
    out: list[dict] = []
    for _, row in rows.sort_values("ts_iso", ascending=False).iterrows():
        meta = _parse_test_comment(str(row.get("comment", "") or ""))
        if not meta:
            continue
        if meta.get("company") and meta.get("company") != company_name:
            continue
        out.append(
            {
                "started_at": meta.get("start_date", ""),
                "target_clicks": int(meta.get("target_clicks", 0) or 0),
                "status": "active",
                "completion_day": "",
                "essence": meta.get("essence", ""),
                "expectations": meta.get("expectations", ""),
                "note": meta.get("note", ""),
            }
        )
    return out


def get_current_campaign_detail(
    *,
    company: str | None,
    date_from: str,
    date_to: str,
    campaign_id: str | None = None,
    target_drr_pct: float = 20.0,
) -> dict:
    company_name, config = resolve_company_config(company)
    perf_client_id = (config.get("perf_client_id") or "").strip() or None
    perf_client_secret = (config.get("perf_client_secret") or "").strip() or None
    seller_client_id = (config.get("seller_client_id") or "").strip() or None
    seller_api_key = (config.get("seller_api_key") or "").strip() or None

    campaigns = get_running_campaigns(client_id=perf_client_id, client_secret=perf_client_secret)
    campaign_options = [
        {"campaign_id": str(item.get("id")), "title": str(item.get("title", "") or ""), "state": str(item.get("state", "") or "")}
        for item in campaigns
        if item.get("id") is not None
    ]
    if not campaign_id:
        return {
            "company": company_name,
            "date_from": date_from,
            "date_to": date_to,
            "campaigns": campaign_options,
            "selected_campaign_id": "",
            "selected_campaign_title": "",
            "sku": "",
            "article": "",
            "current_bid_rub": None,
            "is_single_sku": False,
            "totals": None,
            "parameters": {},
            "weekly_rows": [],
            "daily_rows": [],
            "comments": [],
            "test_history": [],
        }

    selected_id = str(campaign_id)
    selected = next((item for item in campaign_options if item["campaign_id"] == selected_id), None)
    if selected is None:
        selected = {"campaign_id": "", "title": "", "state": ""}
        selected_id = ""
    if not selected_id:
        return {
            "company": company_name,
            "date_from": date_from,
            "date_to": date_to,
            "campaigns": campaign_options,
            "selected_campaign_id": "",
            "selected_campaign_title": "",
            "sku": "",
            "article": "",
            "current_bid_rub": None,
            "is_single_sku": False,
            "totals": None,
            "parameters": {},
            "weekly_rows": [],
            "daily_rows": [],
            "comments": [],
            "test_history": [],
        }

    token = perf_token(client_id=perf_client_id, client_secret=perf_client_secret)
    products_by_campaign_id = load_products_parallel(token, [selected_id], page_size=100)
    items = products_by_campaign_id.get(selected_id, []) or []
    out_sku, _out_title, _out_bid, skus = campaign_display_fields(selected.get("title", ""), items)
    single_sku = out_sku if len(skus) == 1 else ""
    article = _sku_offer_map(skus=[single_sku], seller_client_id=seller_client_id, seller_api_key=seller_api_key).get(single_sku, single_sku)

    _by_sku, _by_day, by_day_sku = seller_analytics_sku_day(
        date_from,
        date_to,
        limit=1000,
        client_id=seller_client_id,
        api_key=seller_api_key,
    )
    _daily, ads_daily_by_campaign = fetch_ads_daily_totals(
        token,
        date_from,
        date_to,
        [selected_id],
        10,
        return_by_campaign=True,
    )
    daily_rows = build_campaign_daily_rows(
        campaign_id=selected_id,
        date_from=date_from,
        date_to=date_to,
        seller_by_day_sku=by_day_sku,
        ads_daily_by_campaign=ads_daily_by_campaign,
        target_drr=float(target_drr_pct) / 100.0,
        items=items,
    )
    daily_df = pd.DataFrame(daily_rows)
    if daily_df.empty:
        weekly_df = pd.DataFrame()
        totals = None
    else:
        weekly_df = _campaign_weekly_aggregate(daily_df, target_drr_pct=target_drr_pct)
        total_money_spent = float(pd.to_numeric(daily_df.get("money_spent", 0), errors="coerce").fillna(0).sum())
        total_views = float(pd.to_numeric(daily_df.get("views", 0), errors="coerce").fillna(0).sum())
        total_clicks = float(pd.to_numeric(daily_df.get("clicks", 0), errors="coerce").fillna(0).sum())
        total_revenue = float(pd.to_numeric(daily_df.get("total_revenue", 0), errors="coerce").fillna(0).sum())
        total_units = float(pd.to_numeric(daily_df.get("ordered_units", 0), errors="coerce").fillna(0).sum())
        totals = _round_row(
            {
                "days_in_period": int(pd.to_datetime(daily_df["day"], errors="coerce").dt.date.nunique()),
                "views": total_views,
                "clicks": total_clicks,
                "ctr": (total_clicks / total_views * 100.0) if total_views else 0.0,
                "cr": (total_units / total_clicks * 100.0) if total_clicks else 0.0,
                "ipo": (total_views / total_units) if total_units else 0.0,
                "money_spent": total_money_spent,
                "click_price": (total_money_spent / total_clicks) if total_clicks else 0.0,
                "cpm": (total_money_spent / total_views * 1000.0) if total_views else 0.0,
                "target_cpc": ((total_revenue / total_clicks) if total_clicks else 0.0) * (float(target_drr_pct) / 100.0),
                "total_revenue": total_revenue,
                "ordered_units": total_units,
                "total_drr_pct": (total_money_spent / total_revenue * 100.0) if total_revenue else 0.0,
            }
        )

    bid_log_df = load_bid_changes_df()
    comments_df = load_campaign_comments_df()
    day_bid_map, week_bid_map = _build_bid_change_maps(
        bid_log_df,
        campaign_id=selected_id,
        sku=single_sku,
        date_from=date_from,
        date_to=date_to,
    )
    day_comments, week_comments, all_day_comments, all_week_comments, recent_comments = _build_comment_maps(
        comments_df,
        company_name=company_name,
        campaign_id=selected_id,
    )

    weekly_rows: list[dict] = []
    if not weekly_df.empty:
        weekly_df = weekly_df.sort_values("week", ascending=False)
        for _, row in weekly_df.iterrows():
            week = str(row.get("week", "") or "")
            payload = _round_row(row.to_dict())
            payload["week"] = week
            payload["bid_change"] = week_bid_map.get(week, "")
            payload["comment"] = week_comments.get(week, "")
            payload["comment_all"] = all_week_comments.get(week, "")
            weekly_rows.append(payload)

    daily_out: list[dict] = []
    if not daily_df.empty:
        daily_df = daily_df.sort_values("day", ascending=False)
        for _, row in daily_df.iterrows():
            day = str(row.get("day", "") or "")
            payload = _round_row(row.to_dict())
            payload["day"] = day
            payload["article"] = article
            payload["bid_change"] = day_bid_map.get(day, "")
            payload["comment"] = day_comments.get(day, "")
            payload["comment_all"] = all_day_comments.get(day, "")
            daily_out.append(payload)

    current_bid_rub = _current_bid_rub(items, single_sku) if single_sku else None
    cpc_econ = None
    cpc_econ_min = None
    cpc_econ_max = None
    if totals:
        revenue = _num(totals.get("total_revenue"))
        units = _num(totals.get("ordered_units"))
        clicks = _num(totals.get("clicks"))
        if revenue > 0 and units > 0 and clicks > 0:
            order_value = revenue / units
            cr = units / clicks
            target = float(target_drr_pct) / 100.0
            cpc_econ = order_value * cr * target
            cpc_econ_min = order_value * cr * max(0.0, target - 0.05)
            cpc_econ_max = order_value * cr * min(1.0, target + 0.05)

    return {
        "company": company_name,
        "date_from": date_from,
        "date_to": date_to,
        "campaigns": campaign_options,
        "selected_campaign_id": selected_id,
        "selected_campaign_title": selected.get("title", ""),
        "sku": single_sku or out_sku,
        "article": article,
        "current_bid_rub": round(current_bid_rub, 1) if current_bid_rub is not None else None,
        "is_single_sku": bool(single_sku),
        "totals": totals,
        "parameters": {
            "current_bid_rub": round(current_bid_rub, 1) if current_bid_rub is not None else None,
            "cpc_econ": round(cpc_econ, 1) if cpc_econ is not None else None,
            "cpc_econ_min": round(cpc_econ_min, 1) if cpc_econ_min is not None else None,
            "cpc_econ_max": round(cpc_econ_max, 1) if cpc_econ_max is not None else None,
        },
        "weekly_rows": weekly_rows,
        "daily_rows": daily_out,
        "comments": recent_comments,
        "test_history": _test_history(bid_log_df, campaign_id=selected_id, sku=single_sku, company_name=company_name),
    }
