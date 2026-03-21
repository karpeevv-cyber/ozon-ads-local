# -*- coding: utf-8 -*-
# ui.py FULL REPLACEMENT

import streamlit as st
import pandas as pd
import altair as alt
from datetime import date, timedelta
import time
import logging
import json
from pathlib import Path

from clients_ads import (
    perf_token,
    get_campaigns,
    get_campaign_products_all,
    update_campaign_product_bids,
)
from report import build_report_rows, campaign_display_fields
from ui_formatting import (
    default_window,
    make_view_df,
    build_column_config,
    fmt_rub_1,
    format_date_ddmmyyyy,
)
from ui_styles import style_median_table, BAND_PCT
from clients_seller import seller_analytics_stocks
from bid_ui_helpers import (
    apply_bid_and_log,
    add_bid_column_period,
    add_bid_columns_daily,
    add_bid_columns_weekly,
    load_bid_log_df,
)
from ui_data import (
    fetch_running_campaigns_cached,
    fetch_ads_stats_by_campaign_cached,
    fetch_ads_daily_totals_cached,
    compute_daily_breakdown,
    fetch_products_by_campaign_cached,
    build_campaign_daily_rows,
    build_campaign_daily_rows_cached,
    calc_cpc_econ_only,
    compute_cpc_econ_range_map,
    campaign_weekly_aggregate,
    seller_analytics_sku_day_cached,
)
from ui_helpers import (
    load_ui_state_cache,
    save_ui_state_cache,
    make_ui_state_cache_key,
    normalize_ui_state_cache,
    get_ui_state_entry,
    save_ui_state_entry,
    load_campaign_comments,
    append_campaign_comment,
    load_company_configs,
    default_company_from_env,
)
from ui_tabs_misc import render_tab4
from ui_finance_tab import render_finance_tab
from ui_stocks_tab import render_stocks_tab
from ui_storage_tab import render_storage_tab
from ui_unit_economics_tab import render_unit_economics_tab, load_unit_economics_daily_summary
from ui_unit_economics_products_tab import render_unit_economics_products_tab
from ui_trends_tab import render_trends_tab

# ---------------- UI ----------------

LOG_PATH = Path("app.log")
logger = logging.getLogger("ozon_ads")
if not logger.handlers:
    logger.setLevel(logging.INFO)
    handler = logging.FileHandler(LOG_PATH, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logger.addHandler(handler)

st.set_page_config(page_title="Ozon Ads ? Report UI", layout="wide")
st.title("Ozon Ads ? Report UI (MVP)")

UI_STATE_CACHE_PATH = "ui_state_cache.pkl"
COMMENTS_PATH = "campaign_comments.csv"
TEST_META_PREFIX = "__test_meta__:"


@st.cache_data(show_spinner=False, ttl=60)
def _load_comments_cached(path: str):
    return load_campaign_comments(path)


@st.cache_data(show_spinner=False, ttl=60)
def _load_bid_log_cached():
    return load_bid_log_df()


@st.cache_data(show_spinner=False, ttl=900)
def _load_sku_offer_map_for_articles(*, seller_client_id: str, seller_api_key: str, skus: tuple[str, ...]) -> dict[str, str]:
    out: dict[str, str] = {}
    sku_values = [str(s).strip() for s in skus if str(s).strip().isdigit()]
    chunk = 200
    for i in range(0, len(sku_values), chunk):
        batch = sku_values[i : i + chunk]
        resp = seller_analytics_stocks(
            skus=batch,
            client_id=seller_client_id,
            api_key=seller_api_key,
        )
        items = resp.get("items", []) or []
        for it in items:
            sku = it.get("sku")
            if sku is None:
                continue
            out[str(sku)] = str(it.get("offer_id") or "").strip()
    return out


def _build_test_comment_payload(*, start_date: str, target_clicks: int, essence: str, expectations: str, note: str = "", company: str = "") -> str:
    payload = {
        "start_date": str(start_date).strip(),
        "target_clicks": int(target_clicks),
        "essence": str(essence or "").strip(),
        "expectations": str(expectations or "").strip(),
        "note": str(note or "").strip(),
        "company": str(company or "").strip(),
    }
    return TEST_META_PREFIX + json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def _parse_test_comment_payload(comment: str):
    text = str(comment or "").strip()
    if not text.startswith(TEST_META_PREFIX):
        return None
    try:
        raw = json.loads(text[len(TEST_META_PREFIX):])
    except Exception:
        return None
    start_date = str(raw.get("start_date", raw.get("date_from", "")) or "").strip()
    target_clicks_raw = raw.get("target_clicks", 0)
    try:
        target_clicks = int(float(str(target_clicks_raw).strip().replace(",", ".")))
    except Exception:
        target_clicks = 0
    return {
        "start_date": start_date,
        "target_clicks": target_clicks,
        "essence": str(raw.get("essence", "") or "").strip(),
        "expectations": str(raw.get("expectations", "") or "").strip(),
        "note": str(raw.get("note", "") or "").strip(),
        "company": str(raw.get("company", "") or "").strip(),
    }


def _get_active_test_map(df: pd.DataFrame, *, on_day: date | None = None) -> dict[tuple[str, str], dict[str, str]]:
    if df is None or df.empty:
        return {}
    return {}


def _get_latest_test_change(df: pd.DataFrame, *, campaign_id: str, sku: str):
    if df is None or df.empty:
        return None
    rows = df[df["reason"].astype(str) == "Test"].copy() if "reason" in df.columns else pd.DataFrame()
    if rows.empty:
        return None
    rows = rows[
        (rows["campaign_id"].astype(str) == str(campaign_id))
        & (rows["sku"].astype(str) == str(sku))
    ].copy()
    if rows.empty:
        return None
    rows["_test_meta"] = rows["comment"].apply(_parse_test_comment_payload)
    rows = rows[rows["_test_meta"].notna()].copy()
    if rows.empty:
        return None
    rows = rows.sort_values("ts_iso", ascending=False)
    return rows.iloc[0]["_test_meta"]


def _list_test_entries(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty or "reason" not in df.columns:
        return pd.DataFrame(columns=["ts_iso", "date", "campaign_id", "sku", "start_date", "target_clicks", "essence", "expectations", "note"])
    rows = df[df["reason"].astype(str) == "Test"].copy()
    if rows.empty:
        return pd.DataFrame(columns=["ts_iso", "date", "campaign_id", "sku", "start_date", "target_clicks", "essence", "expectations", "note"])
    rows["_test_meta"] = rows["comment"].apply(_parse_test_comment_payload)
    rows = rows[rows["_test_meta"].notna()].copy()
    if rows.empty:
        return pd.DataFrame(columns=["ts_iso", "date", "campaign_id", "sku", "start_date", "target_clicks", "essence", "expectations", "note"])
    rows["start_date"] = rows["_test_meta"].apply(lambda x: x.get("start_date", ""))
    rows["target_clicks"] = rows["_test_meta"].apply(lambda x: int(x.get("target_clicks", 0) or 0))
    rows["essence"] = rows["_test_meta"].apply(lambda x: x.get("essence", ""))
    rows["expectations"] = rows["_test_meta"].apply(lambda x: x.get("expectations", ""))
    rows["note"] = rows["_test_meta"].apply(lambda x: x.get("note", ""))
    rows["company"] = rows["_test_meta"].apply(lambda x: x.get("company", ""))
    return rows[["ts_iso", "date", "campaign_id", "sku", "company", "start_date", "target_clicks", "essence", "expectations", "note"]].copy()


def _daterange_days(date_from_iso: str, date_to_iso: str) -> list[str]:
    try:
        d_from = date.fromisoformat(str(date_from_iso))
        d_to = date.fromisoformat(str(date_to_iso))
    except Exception:
        return []
    out: list[str] = []
    d = d_from
    while d <= d_to:
        out.append(d.isoformat())
        d += timedelta(days=1)
    return out


def _build_test_daily_rows(*, campaign_id: str, sku: str, date_from_iso: str, date_to_iso: str, seller_client_id: str, seller_api_key: str, perf_client_id: str, perf_client_secret: str) -> pd.DataFrame:
    days = _daterange_days(date_from_iso, date_to_iso)
    if not days:
        return pd.DataFrame(columns=["day", "views", "clicks", "ctr", "cr", "money_spent", "click_price", "total_revenue", "total_drr_pct", "ordered_units"])
    _by_sku, _by_day, by_day_sku = seller_analytics_sku_day_cached(
        date_from_iso,
        date_to_iso,
        limit=1000,
        seller_client_id=seller_client_id,
        seller_api_key=seller_api_key,
    )
    _daily, ads_daily_by_campaign = fetch_ads_daily_totals_cached(
        perf_client_id,
        perf_client_secret,
        date_from_iso,
        date_to_iso,
        [str(campaign_id)],
        10,
        return_by_campaign=True,
    )
    rows: list[dict] = []
    for day_str in days:
        stats = ads_daily_by_campaign.get((day_str, str(campaign_id)), {}) or {}
        views = int(stats.get("views", 0) or 0)
        clicks = int(stats.get("clicks", 0) or 0)
        money_spent = float(stats.get("money_spent", 0.0) or 0.0)
        click_price = float(stats.get("click_price", 0.0) or 0.0)
        revenue, units = by_day_sku.get((day_str, str(sku)), (0.0, 0))
        ctr = (clicks / views * 100.0) if views else 0.0
        cr = (int(units) / clicks * 100.0) if clicks else 0.0
        drr = (money_spent / float(revenue) * 100.0) if float(revenue) else 0.0
        rows.append(
            {
                "day": day_str,
                "views": views,
                "clicks": clicks,
                "ctr": ctr,
                "cr": cr,
                "money_spent": money_spent,
                "click_price": click_price,
                "total_revenue": float(revenue),
                "total_drr_pct": drr,
                "ordered_units": int(units),
            }
        )
    return pd.DataFrame(rows)


def _summarize_test_metrics(df: pd.DataFrame) -> dict[str, float]:
    if df is None or df.empty:
        return {
            "views": 0.0,
            "clicks": 0.0,
            "ctr": 0.0,
            "cr": 0.0,
            "money_spent": 0.0,
            "click_price": 0.0,
            "total_revenue": 0.0,
            "total_drr_pct": 0.0,
        }
    views = float(pd.to_numeric(df.get("views", 0), errors="coerce").fillna(0).sum())
    clicks = float(pd.to_numeric(df.get("clicks", 0), errors="coerce").fillna(0).sum())
    money_spent = float(pd.to_numeric(df.get("money_spent", 0), errors="coerce").fillna(0).sum())
    revenue = float(pd.to_numeric(df.get("total_revenue", 0), errors="coerce").fillna(0).sum())
    units = float(pd.to_numeric(df.get("ordered_units", 0), errors="coerce").fillna(0).sum())
    return {
        "views": views,
        "clicks": clicks,
        "ctr": (clicks / views * 100.0) if views else 0.0,
        "cr": (units / clicks * 100.0) if clicks else 0.0,
        "money_spent": money_spent,
        "click_price": (money_spent / clicks) if clicks else 0.0,
        "total_revenue": revenue,
        "total_drr_pct": (money_spent / revenue * 100.0) if revenue else 0.0,
    }


def _evaluate_test_entry(*, entry: pd.Series, seller_client_id: str, seller_api_key: str, perf_client_id: str, perf_client_secret: str) -> dict:
    start_date = str(entry.get("start_date", "") or "").strip()
    if not start_date:
        start_date = str(entry.get("date", "") or "").strip()
    target_clicks = int(entry.get("target_clicks", 0) or 0)
    campaign_id = str(entry.get("campaign_id", "") or "").strip()
    sku = str(entry.get("sku", "") or "").strip()
    today_iso = date.today().isoformat()
    live_df = _build_test_daily_rows(
        campaign_id=campaign_id,
        sku=sku,
        date_from_iso=start_date,
        date_to_iso=today_iso,
        seller_client_id=seller_client_id,
        seller_api_key=seller_api_key,
        perf_client_id=perf_client_id,
        perf_client_secret=perf_client_secret,
    )
    if live_df.empty:
        return {
            "status": "active",
            "completion_day": "",
            "test_summary": _summarize_test_metrics(live_df),
            "baseline_summary": _summarize_test_metrics(pd.DataFrame()),
            "actual_clicks": 0,
        }
    live_df = live_df.sort_values("day").reset_index(drop=True)
    live_df["cum_clicks"] = pd.to_numeric(live_df["clicks"], errors="coerce").fillna(0).cumsum()
    completion_day = ""
    if target_clicks > 0:
        reached = live_df[live_df["cum_clicks"] >= target_clicks]
        if not reached.empty:
            completion_day = str(reached.iloc[0]["day"])
    status = "completed" if completion_day else "active"
    test_rows = live_df if not completion_day else live_df[live_df["day"].astype(str) <= completion_day].copy()
    actual_clicks = int(pd.to_numeric(test_rows.get("clicks", 0), errors="coerce").fillna(0).sum())
    test_summary = _summarize_test_metrics(test_rows)
    baseline_summary = _summarize_test_metrics(pd.DataFrame())
    if status == "completed":
        try:
            baseline_end = date.fromisoformat(start_date) - timedelta(days=1)
            baseline_start = baseline_end - timedelta(days=180)
            baseline_df = _build_test_daily_rows(
                campaign_id=campaign_id,
                sku=sku,
                date_from_iso=baseline_start.isoformat(),
                date_to_iso=baseline_end.isoformat(),
                seller_client_id=seller_client_id,
                seller_api_key=seller_api_key,
                perf_client_id=perf_client_id,
                perf_client_secret=perf_client_secret,
            )
            if not baseline_df.empty:
                baseline_df = baseline_df.sort_values("day", ascending=False).reset_index(drop=True)
                baseline_df["cum_clicks"] = pd.to_numeric(baseline_df["clicks"], errors="coerce").fillna(0).cumsum()
                target_baseline_clicks = max(actual_clicks, target_clicks)
                reached_prev = baseline_df[baseline_df["cum_clicks"] >= target_baseline_clicks]
                if not reached_prev.empty:
                    last_idx = int(reached_prev.index[0])
                    baseline_rows = baseline_df.iloc[: last_idx + 1].copy()
                else:
                    baseline_rows = baseline_df.copy()
                baseline_summary = _summarize_test_metrics(baseline_rows)
        except Exception:
            baseline_summary = _summarize_test_metrics(pd.DataFrame())
    return {
        "status": status,
        "completion_day": completion_day,
        "test_summary": test_summary,
        "baseline_summary": baseline_summary,
        "actual_clicks": actual_clicks,
    }

company_configs = load_company_configs(".env")
if not company_configs:
    default_company = default_company_from_env()
    if any(default_company.values()):
        company_configs = {"default": default_company}

company_keys = list(company_configs.keys())

# Sidebar
st.sidebar.header("Parameters")
selected_company = None
if company_keys:
    if "selected_company" not in st.session_state:
        cached_company = normalize_ui_state_cache(load_ui_state_cache(UI_STATE_CACHE_PATH)).get("selected_company")
        if cached_company:
            st.session_state.selected_company = cached_company
    default_company = st.session_state.get("selected_company")
    if default_company not in company_keys:
        default_company = company_keys[0]
    selected_company = st.sidebar.selectbox(
        "Company",
        options=company_keys,
        index=company_keys.index(default_company),
        key="company_pick",
    )
else:
    st.sidebar.warning("No companies found in .env.")

if selected_company:
    selected_creds = company_configs.get(selected_company) or {}
else:
    selected_creds = default_company_from_env()

perf_client_id = (selected_creds.get("perf_client_id") or "").strip()
perf_client_secret = (selected_creds.get("perf_client_secret") or "").strip()
seller_client_id = (selected_creds.get("seller_client_id") or "").strip()
seller_api_key = (selected_creds.get("seller_api_key") or "").strip()

prev_company = st.session_state.get("selected_company")
if selected_company and prev_company != selected_company:
    st.session_state.selected_company = selected_company
    try:
        cached = normalize_ui_state_cache(load_ui_state_cache(UI_STATE_CACHE_PATH))
        cached["selected_company"] = selected_company
        save_ui_state_cache(cached, UI_STATE_CACHE_PATH)
    except Exception:
        pass
    for k in [
        "rows_csv",
        "rows_count",
        "daily_rows",
        "ads_daily_by_campaign",
        "products_by_campaign_id",
        "running_ids",
        "running_count",
        "campaign_daily_rows",
        "picked_campaign_id",
        "by_day_sku",
        "data_company",
        "cpc_econ_range_map",
        "cpc_econ_bounds_map",
    ]:
        st.session_state.pop(k, None)
    st.session_state.last_go_ts = None
    st.session_state.last_error = ""
    st.session_state.cache_loaded = False

def _resolve_sidebar_date_defaults(company_name: str | None) -> tuple[date, date]:
    return default_window()


if st.session_state.get("_sidebar_dates_company") != selected_company:
    d_from_default, d_to_default = _resolve_sidebar_date_defaults(selected_company)
    st.session_state.sidebar_date_from = d_from_default
    st.session_state.sidebar_date_to = d_to_default
    st.session_state._sidebar_dates_company = selected_company
elif "sidebar_date_from" not in st.session_state or "sidebar_date_to" not in st.session_state:
    d_from_default, d_to_default = _resolve_sidebar_date_defaults(selected_company)
    st.session_state.sidebar_date_from = d_from_default
    st.session_state.sidebar_date_to = d_to_default

st.sidebar.date_input("date_from", key="sidebar_date_from")
st.sidebar.date_input("date_to", key="sidebar_date_to")
date_from = st.session_state.sidebar_date_from
date_to = st.session_state.sidebar_date_to

target_drr_pct = st.sidebar.number_input("target drr", min_value=0.0, max_value=100.0, value=20.0, step=0.5)
target_drr = float(target_drr_pct) / 100.0

current_params = {
    "selected_company": selected_company,
    "date_from": str(date_from),
    "date_to": str(date_to),
}
prev_params = st.session_state.get("_last_params")
if prev_params and prev_params != current_params:
    for k in [
        "rows_csv",
        "daily_rows",
        "ads_daily_by_campaign",
        "products_by_campaign_id",
        "by_day_sku",
        "cpc_econ_range_map",
        "cpc_econ_bounds_map",
    ]:
        st.session_state.pop(k, None)
    st.session_state.last_go_ts = None
    st.session_state.last_error = ""
    st.session_state.cache_loaded = False
st.session_state._last_params = current_params

batch_size = 15
include_products = True

# Load UI cache on cold start (avoid re-GO after refresh)
if "rows_csv" not in st.session_state:
    cached = normalize_ui_state_cache(load_ui_state_cache(UI_STATE_CACHE_PATH))
    if cached:
        cache_key = make_ui_state_cache_key(selected_company, str(date_from), str(date_to))
        cached_entry = get_ui_state_entry(cached, cache_key)
        if cached_entry:
            st.session_state.update(cached_entry)
            st.session_state.cache_loaded = True
            st.session_state.data_company = cached_entry.get("selected_company")
        else:
            st.session_state.cache_loaded = False

# ---- GO button: load data only on explicit click ----
    refresh_stocks = False

go = st.sidebar.button("Update data")
refresh_finance = go

if go:
    try:
        st.session_state.last_go_ts = time.time()
        st.session_state.go_stage = "start"
        with st.spinner("Loading data..."):
            token = perf_token(perf_client_id, perf_client_secret)

            campaigns = get_campaigns(token)
            running = [c for c in campaigns if c.get("state") == "CAMPAIGN_STATE_RUNNING"]
            running_ids = [str(c["id"]) for c in running]

            # 1) Seller analytics for period (single call, 1 min cooldown)
            by_sku, by_day, by_day_sku = seller_analytics_sku_day_cached(
                str(date_from),
                str(date_to),
                limit=1000,
                seller_client_id=seller_client_id,
                seller_api_key=seller_api_key,
            )
            st.session_state.go_stage = "seller_loaded"

            # 2) Ads stats for period for all running campaigns
            stats_by_campaign_id = fetch_ads_stats_by_campaign_cached(
                perf_client_id,
                perf_client_secret,
                str(date_from),
                str(date_to),
                running_ids,
                int(batch_size),
            )
            st.session_state.go_stage = "ads_loaded"

            products_by_campaign_id = fetch_products_by_campaign_cached(
                perf_client_id,
                perf_client_secret,
                running_ids,
                include_products,
            )
            st.session_state.go_stage = "products_loaded"

            # 4) Build report rows (campaigns + GRAND_TOTAL)
            rows_csv, _ = build_report_rows(

                running_campaigns=running,
                stats_by_campaign_id=stats_by_campaign_id,
                sales_map=by_sku,
                products_by_campaign_id=products_by_campaign_id,
            )
            st.session_state.go_stage = "rows_built"

            # 5) Ads daily totals + merge with Seller by_day
            ads_daily_rows, ads_daily_by_campaign = fetch_ads_daily_totals_cached(
                perf_client_id,
                perf_client_secret,
                str(date_from),
                str(date_to),
                running_ids,
                int(batch_size),
                return_by_campaign=True,
            )
            daily_rows = compute_daily_breakdown(ads_daily_rows, by_day, target_drr=target_drr)
            st.session_state.go_stage = "daily_built"

            st.session_state.rows_csv = rows_csv
            st.session_state.rows_count = len(rows_csv)
            st.session_state.products_by_campaign_id = products_by_campaign_id
            st.session_state.running_ids = [str(c.get("id")) for c in running]
            st.session_state.running_count = len(running)
            st.session_state.daily_rows = daily_rows
            st.session_state.ads_daily_by_campaign = ads_daily_by_campaign
            st.session_state.by_day_sku = by_day_sku
            st.session_state.data_company = selected_company
            st.session_state.date_from = str(date_from)
            st.session_state.date_to = str(date_to)
            st.session_state.target_drr = target_drr
            st.session_state.target_drr_pct = target_drr_pct
            econ_map, econ_bounds = compute_cpc_econ_range_map(
                campaign_ids=[str(cid) for cid in running_ids],
                date_from=str(date_from),
                date_to=str(date_to),
                seller_by_day_sku=by_day_sku,
                ads_daily_by_campaign=ads_daily_by_campaign,
                products_by_campaign_id=products_by_campaign_id,
                target_drr=target_drr,
            )
            st.session_state.cpc_econ_range_map = econ_map
            st.session_state.cpc_econ_bounds_map = econ_bounds
            st.session_state.go_stage = "state_saved"
            st.session_state.cache_loaded = False

            cache_key = make_ui_state_cache_key(selected_company, str(date_from), str(date_to))
            save_ui_state_entry(
                UI_STATE_CACHE_PATH,
                cache_key,
                {
                    "rows_csv": rows_csv,
                    "rows_count": len(rows_csv),
                    "products_by_campaign_id": products_by_campaign_id,
                    "running_ids": [str(c.get("id")) for c in running],
                    "running_count": len(running),
                    "daily_rows": daily_rows,
                    "ads_daily_by_campaign": ads_daily_by_campaign,
                    "by_day_sku": by_day_sku,
                    "date_from": str(date_from),
                    "date_to": str(date_to),
                    "target_drr": target_drr,
                    "target_drr_pct": target_drr_pct,
                    "selected_company": selected_company,
                    "cpc_econ_range_map": econ_map,
                    "cpc_econ_bounds_map": econ_bounds,
                },
                selected_company=selected_company,
            )
        st.session_state.last_error = ""
        st.session_state.go_stage = "done"
    except Exception as e:
        st.session_state.last_error = repr(e)
        st.session_state.go_stage = f"error:{repr(e)}"
        logger.exception("GO failed")
# ---------------- Render (no API calls here) ----------------

rows_csv = st.session_state.get("rows_csv")
daily_rows = st.session_state.get("daily_rows")
target_drr = st.session_state.get("target_drr", target_drr)
products_by_campaign_id = st.session_state.get("products_by_campaign_id", {})
running_ids = st.session_state.get("running_ids", [])
ads_daily_by_campaign = st.session_state.get("ads_daily_by_campaign", {})
by_day_sku = st.session_state.get("by_day_sku")
comments_df = _load_comments_cached(COMMENTS_PATH)
if comments_df is not None and not comments_df.empty:
    if "company" in comments_df.columns and selected_company:
        comments_df = comments_df[comments_df["company"].astype(str) == str(selected_company)].copy()
    elif "company" in comments_df.columns and not selected_company:
        comments_df = comments_df[comments_df["company"].astype(str).str.strip() == ""].copy()
data_company = st.session_state.get("data_company")
if data_company and selected_company and data_company != selected_company:
    rows_csv = None
    daily_rows = None

tab_options = [
    "Main",
    "All campaigns",
    "Current campaigns",
    "Tests",
    "Unit Economics",
    "Unit Economics Products",
    "Finance balance",
    "Stocks",
    "Storage",
    "Search Trends",
    "Formulas",
]
selected_tab = st.radio(
    "Section",
    options=tab_options,
    horizontal=True,
    label_visibility="collapsed",
)

if selected_tab == "Search Trends":
    render_trends_tab(
        date_from=date_from,
        date_to=date_to,
        seller_client_id=seller_client_id,
        seller_api_key=seller_api_key,
        company_name=selected_company,
    )
    st.stop()

if not rows_csv:
    if st.session_state.get("last_error"):
        st.error(f"GO error: {st.session_state.get('last_error')}")
    else:
        last_go_ts = st.session_state.get("last_go_ts")
        if last_go_ts and (time.time() - last_go_ts) < 120:
            rows_count = st.session_state.get("rows_count")
            running_count = st.session_state.get("running_count")
            st.error(
                f"GO finished without data. rows={rows_count}, running={running_count}. Check errors/limits."
            )
    st.info("No cached data for selected params. Click Update data.")
    st.stop()
else:
    if st.session_state.get("cache_loaded"):
        st.caption("Loaded cached data. Press GO to refresh.")

df = pd.DataFrame(rows_csv)
df_campaigns = df[df["campaign_id"] != "GRAND_TOTAL"].copy()
df_total = df[df["campaign_id"] == "GRAND_TOTAL"].copy()

def _combine_comment_values(values) -> str:
    out = []
    seen = set()
    for v in values:
        txt = str(v or "").strip()
        if not txt or txt in seen:
            continue
        seen.add(txt)
        out.append(txt)
    return "\n\n".join(out)


def _combine_comments_with_day(df_comments: pd.DataFrame) -> str:
    out = []
    seen = set()
    if df_comments is None or df_comments.empty:
        return ""
    df_sorted = df_comments.sort_values(["day", "ts"], ascending=[False, False])
    for _, row in df_sorted.iterrows():
        txt = str(row.get("comment", "") or "").strip()
        if not txt:
            continue
        day_str = str(row.get("day", "") or "").strip()
        item = f"{day_str}: {txt}" if day_str else txt
        if item in seen:
            continue
        seen.add(item)
        out.append(item)
    return "\n\n".join(out)

campaign_title_map = st.session_state.get("campaign_title_map") or {}
if not campaign_title_map:
    try:
        running_for_names = fetch_running_campaigns_cached(perf_client_id, perf_client_secret)
        campaign_title_map = {
            str(c.get("id")): str(c.get("title", "") or "").strip()
            for c in running_for_names
            if c.get("id") is not None
        }
    except Exception:
        campaign_title_map = {}
    st.session_state.campaign_title_map = campaign_title_map

if selected_tab == "Main":
    st.subheader("Итоги по дням (за период)")
    if daily_rows:
        df_daily_raw = pd.DataFrame(daily_rows)
        ebitda_daily = load_unit_economics_daily_summary(
            str(st.session_state.get("date_from", date_from)),
            str(st.session_state.get("date_to", date_to)),
            seller_client_id=seller_client_id,
            seller_api_key=seller_api_key,
            company_name=selected_company,
        )
        if not ebitda_daily.empty and "day" in df_daily_raw.columns:
            df_daily_raw = df_daily_raw.merge(ebitda_daily, on="day", how="left")
        if "ebitda" not in df_daily_raw.columns:
            df_daily_raw["ebitda"] = 0.0
        if "ebitda_pct" not in df_daily_raw.columns:
            df_daily_raw["ebitda_pct"] = 0.0
        df_daily_raw["ebitda"] = pd.to_numeric(df_daily_raw["ebitda"], errors="coerce").fillna(0.0)
        df_daily_raw["ebitda_pct"] = pd.to_numeric(df_daily_raw["ebitda_pct"], errors="coerce").fillna(0.0)
        week_comment_map = {}
        bid_changes_day_map = {}
        bid_changes_week_map = {}
        bid_log_df_tab1 = st.session_state.get("bid_log_df")
        if bid_log_df_tab1 is None:
            bid_log_df_tab1 = _load_bid_log_cached()
            st.session_state.bid_log_df = bid_log_df_tab1
        if bid_log_df_tab1 is not None and not bid_log_df_tab1.empty:
            campaign_ids_set = set(df_campaigns["campaign_id"].astype(str).tolist())
            bid_log_local = bid_log_df_tab1.copy()
            bid_log_local["campaign_id"] = bid_log_local["campaign_id"].astype(str)
            bid_log_local = bid_log_local[bid_log_local["campaign_id"].isin(campaign_ids_set)]
            if not bid_log_local.empty:
                bid_log_local["date"] = pd.to_datetime(bid_log_local["date"], errors="coerce")
                bid_log_local = bid_log_local.dropna(subset=["date"])
                if not bid_log_local.empty:
                    bid_log_local["date_iso"] = bid_log_local["date"].dt.date.astype(str)
                    bid_changes_day_map = bid_log_local.groupby("date_iso").size().to_dict()
                    bid_log_local["week"] = bid_log_local["date"].dt.date.apply(
                        lambda d: d - timedelta(days=d.weekday())
                    ).astype(str)
                    bid_changes_week_map = bid_log_local.groupby("week").size().to_dict()
        if comments_df is not None and not comments_df.empty and "day" in df_daily_raw.columns:
            period_from = str(st.session_state.get("date_from", date_from))
            period_to = str(st.session_state.get("date_to", date_to))
            comments_period = comments_df[
                (comments_df["day"] >= period_from) & (comments_df["day"] <= period_to)
            ].copy()
            if not comments_period.empty:
                comments_period = comments_period.sort_values(["day", "ts"], ascending=[True, False])

                def _merge_day_comments(group: pd.DataFrame) -> str:
                    out = []
                    seen = set()
                    title_map = st.session_state.get("campaign_title_map") or {}
                    for _, row in group.iterrows():
                        txt = str(row.get("comment", "") or "").strip()
                        if not txt:
                            continue
                        cid = str(row.get("campaign_id", "") or "").strip()
                        if cid.lower() == "all":
                            label = "all"
                        else:
                            label = str(title_map.get(cid) or "").strip()
                        item = f"{label}: {txt}" if label else txt
                        if item not in seen:
                            seen.add(item)
                            out.append(item)
                    return "\n\n".join(out)

                day_comment_map = comments_period.groupby("day").apply(_merge_day_comments).to_dict()

                comments_period_week = comments_period.copy()
                comments_period_week["week"] = (
                    pd.to_datetime(comments_period_week["day"], errors="coerce")
                    .dt.to_period("W-SUN")
                    .dt.start_time
                    .dt.date
                    .astype(str)
                )

                def _merge_week_comments(group: pd.DataFrame) -> str:
                    out = []
                    seen = set()
                    for _, row in group.sort_values(["day", "ts"], ascending=[False, False]).iterrows():
                        txt = str(row.get("comment", "") or "").strip()
                        if not txt:
                            continue
                        day_str = str(row.get("day", "") or "").strip()
                        item = f"{day_str}: {txt}" if day_str else txt
                        if item in seen:
                            continue
                        seen.add(item)
                        out.append(item)
                    return "\n\n".join(out)

                week_comment_map = comments_period_week.groupby("week").apply(_merge_week_comments).to_dict()
            else:
                day_comment_map = {}
            df_daily_raw["comment"] = df_daily_raw["day"].astype(str).map(day_comment_map).fillna("")
        else:
            df_daily_raw["comment"] = ""
        if "day" in df_daily_raw.columns:
            df_daily_raw["bid_changes_cnt"] = (
                df_daily_raw["day"].astype(str).map(bid_changes_day_map).fillna(0).astype(int)
            )
        else:
            df_daily_raw["bid_changes_cnt"] = 0
        if "day" in df_daily_raw.columns:
            df_daily_raw["day_dt"] = pd.to_datetime(df_daily_raw["day"], errors="coerce")
            df_daily_raw = df_daily_raw.sort_values("day_dt", ascending=False).drop(columns=["day_dt"], errors="ignore")
        if "day" in df_daily_raw.columns and "total_revenue" in df_daily_raw.columns:
            df_chart = df_daily_raw.copy()
            df_chart["day_dt"] = pd.to_datetime(df_chart["day"], errors="coerce")
            df_chart = df_chart.sort_values("day_dt")
            chart_df = df_chart[["day_dt", "total_revenue", "money_spent", "total_drr_pct"]].copy()
            chart_df = chart_df.dropna(subset=["day_dt"])
            if "money_spent" not in chart_df.columns:
                chart_df["money_spent"] = 0
            if "total_drr_pct" not in chart_df.columns:
                chart_df["total_drr_pct"] = 0
            chart_df["total_drr_pct"] = pd.to_numeric(chart_df["total_drr_pct"], errors="coerce")

            base = alt.Chart(chart_df).encode(x=alt.X("day_dt:T", title="Day"))
            rev_spend = base.transform_fold(
                ["total_revenue", "money_spent"],
                as_=["metric", "value"],
            ).mark_line().encode(
                y=alt.Y("value:Q", title="RUB"),
                color=alt.Color("metric:N", title=None),
            )
            drr = base.mark_line(strokeDash=[4, 2], color="#888").encode(
                y=alt.Y("total_drr_pct:Q", title="DRR %"),
            )

            chart = (
                alt.layer(rev_spend, drr)
                .resolve_scale(y="independent")
                .properties(height=280, padding={"left": 5, "right": 5, "top": 5, "bottom": 40})
            )
            st.altair_chart(chart, width="stretch")
        df_daily = make_view_df(df_daily_raw).drop(columns=["vor", "target_cpc"], errors="ignore")
        daily_cols = [
            "day",
            "total_revenue",
            "total_drr_pct",
            "money_spent",
            "views",
            "clicks",
            "ordered_units",
            "ctr",
            "cr",
            "organic_pct",
            "bid_changes_cnt",
            "comment",
        ]
        df_daily = df_daily[[c for c in daily_cols if c in df_daily.columns]]
        if "day" in df_daily.columns:
            df_daily["day"] = format_date_ddmmyyyy(df_daily["day"])
        metrics_daily_totals = {
            "total_drr_pct": "lower",
            "ctr": "higher",
            "cr": "higher",
        }
        st.markdown("### Итоги по неделям (за период)")
        df_weekly_main_raw = campaign_weekly_aggregate(df_daily_raw, target_drr=target_drr)
        if not df_weekly_main_raw.empty:
            if "days_in_period" in df_weekly_main_raw.columns:
                days_den = pd.to_numeric(df_weekly_main_raw["days_in_period"], errors="coerce").replace(0, pd.NA)
                for src_col, dst_col in (
                    ("total_revenue", "total_revenue_per_day"),
                    ("money_spent", "money_spent_per_day"),
                    ("views", "views_per_day"),
                    ("clicks", "clicks_per_day"),
                    ("ordered_units", "ordered_units_per_day"),
                ):
                    if src_col in df_weekly_main_raw.columns:
                        src = pd.to_numeric(df_weekly_main_raw[src_col], errors="coerce").fillna(0)
                        df_weekly_main_raw[dst_col] = (src / days_den).fillna(0).round(0)
            if "week" in df_weekly_main_raw.columns:
                df_weekly_main_raw["week_dt"] = pd.to_datetime(df_weekly_main_raw["week"], errors="coerce")
                df_weekly_main_raw = df_weekly_main_raw.sort_values("week_dt", ascending=False).drop(columns=["week_dt"], errors="ignore")
                df_weekly_main_raw["comment"] = df_weekly_main_raw["week"].astype(str).map(week_comment_map).fillna("")
                df_weekly_main_raw["bid_changes_cnt"] = (
                    df_weekly_main_raw["week"].astype(str).map(bid_changes_week_map).fillna(0).astype(int)
                )
            df_weekly_main = make_view_df(df_weekly_main_raw).drop(columns=["vor", "target_cpc"], errors="ignore")
            weekly_cols = [
                "week",
                "total_revenue",
                "total_drr_pct",
                "ebitda",
                "ebitda_pct",
                "total_revenue_per_day",
                "money_spent_per_day",
                "views_per_day",
                "clicks_per_day",
                "ordered_units_per_day",
                "ctr",
                "cr",
                "organic_pct",
                "bid_changes_cnt",
                "comment",
            ]
            df_weekly_main = df_weekly_main[[c for c in weekly_cols if c in df_weekly_main.columns]]
            if "week" in df_weekly_main.columns:
                df_weekly_main["week"] = format_date_ddmmyyyy(df_weekly_main["week"])
            metrics_weekly_main = {
                "total_drr_pct": "lower",
                "ebitda": "higher",
                "ebitda_pct": "higher",
                "ctr": "higher",
                "cr": "higher",
            }
            weekly_cfg = build_column_config(df_weekly_main)
            weekly_label_map = {
                "total_revenue": "revenue",
                "ordered_units_per_day": "units/day",
                "money_spent_per_day": "spent/day",
                "total_revenue_per_day": "revenue/day",
                "total_drr_pct": "drr",
                "views_per_day": "views/day",
                "clicks_per_day": "clicks/day",
            }
            excluded_progress_cols_weekly = {"comment", "bid_changes_cnt", "week", "days_in_period"}
            money_progress_cols = {
                "money_spent",
                "money_spent_per_day",
                "total_revenue",
                "total_revenue_per_day",
                "click_price",
                "bid",
                "orders_money_ads",
                "ebitda",
            }
            pct_progress_cols = {
                "total_drr_pct",
                "ctr",
                "cr",
                "organic_pct",
                "ebitda_pct",
                "total_drr",
                "total_drr_after_chng",
                "vor",
            }
            one_decimal_cols = set()

            for col in df_weekly_main.columns:
                if col in excluded_progress_cols_weekly:
                    continue
                s_num = pd.to_numeric(df_weekly_main[col], errors="coerce")
                if s_num.isna().all():
                    continue

                min_val = float(s_num.fillna(0).min())
                max_val = float(s_num.fillna(0).max())
                label = weekly_label_map.get(col, col)
                if col in money_progress_cols:
                    fmt = "%.0f ₽"
                elif col in pct_progress_cols or col.endswith("_pct"):
                    fmt = "%.1f%%"
                elif col in one_decimal_cols:
                    fmt = "%.1f"
                else:
                    fmt = "%.0f"

                weekly_cfg[col] = st.column_config.ProgressColumn(
                    label,
                    min_value=min(0.0, min_val),
                    max_value=max(1.0, max_val),
                    format=fmt,
                    width="small",
                    )
            for col in df_weekly_main.columns:
                if col in weekly_cfg:
                    continue
                weekly_cfg[col] = st.column_config.TextColumn(
                    weekly_label_map.get(col, col),
                    width="small",
                )
            st.dataframe(
                df_weekly_main,
                width="stretch",
                hide_index=True,
                column_config=weekly_cfg,
            )
        st.markdown("<div style='height: 20px;'></div>", unsafe_allow_html=True)
        daily_cfg = build_column_config(df_daily)
        excluded_progress_cols = {"comment", "bid_changes_cnt", "day"}
        money_progress_cols = {"money_spent", "total_revenue", "click_price", "bid", "orders_money_ads"}
        pct_progress_cols = {
            "total_drr_pct",
            "ctr",
            "cr",
            "organic_pct",
            "total_drr",
            "total_drr_after_chng",
            "vor",
        }
        one_decimal_cols = set()

        for col in df_daily.columns:
            if col in excluded_progress_cols:
                continue
            s_num = pd.to_numeric(df_daily[col], errors="coerce")
            if s_num.isna().all():
                continue

            min_val = float(s_num.fillna(0).min())
            max_val = float(s_num.fillna(0).max())
            if col in money_progress_cols:
                fmt = "%.0f ₽"
            elif col in pct_progress_cols or col.endswith("_pct"):
                fmt = "%.1f%%"
            elif col in one_decimal_cols:
                fmt = "%.1f"
            else:
                fmt = "%.0f"

            daily_cfg[col] = st.column_config.ProgressColumn(
                col,
                min_value=min(0.0, min_val),
                max_value=max(1.0, max_val),
                format=fmt,
                width="small",
            )
        for col in df_daily.columns:
            if col in daily_cfg:
                continue
            daily_cfg[col] = st.column_config.TextColumn(col, width="small")
        st.dataframe(
            df_daily,
            width="stretch",
            hide_index=True,
            column_config=daily_cfg,
        )
    else:
        st.warning("Нет данных по дням.")

if selected_tab == "All campaigns":
    sku_offer_map_for_articles = {}
    if seller_client_id and seller_api_key and products_by_campaign_id:
        all_skus_for_articles = []
        for items in (products_by_campaign_id or {}).values():
            for it in items or []:
                sku_val = str(it.get("sku") or "").strip()
                if sku_val:
                    all_skus_for_articles.append(sku_val)
        all_skus_for_articles = tuple(dict.fromkeys(all_skus_for_articles))
        if all_skus_for_articles:
            try:
                sku_offer_map_for_articles = _load_sku_offer_map_for_articles(
                    seller_client_id=seller_client_id,
                    seller_api_key=seller_api_key,
                    skus=all_skus_for_articles,
                )
            except Exception:
                sku_offer_map_for_articles = {}

    try:
        loaded_from = date.fromisoformat(str(st.session_state.get("date_from", date_from)))
        loaded_to = date.fromisoformat(str(st.session_state.get("date_to", date_to)))
    except Exception:
        loaded_from = date_from
        loaded_to = date_to

    st.caption("Local date filter (within loaded range)")
    if "tab2_one_day" not in st.session_state:
        st.session_state.tab2_one_day = False
    if "tab2_day" not in st.session_state:
        st.session_state.tab2_day = loaded_to
    if "tab2_range_valid" not in st.session_state:
        st.session_state.tab2_range_valid = (loaded_from, loaded_to)

    if st.session_state.tab2_day < loaded_from or st.session_state.tab2_day > loaded_to:
        st.session_state.tab2_day = loaded_to
    cur_from, cur_to = st.session_state.tab2_range_valid
    if cur_from < loaded_from or cur_to > loaded_to:
        st.session_state.tab2_range_valid = (loaded_from, loaded_to)
        cur_from, cur_to = st.session_state.tab2_range_valid
    if cur_from < loaded_from or cur_to > loaded_to:
        st.session_state.tab2_range = (loaded_from, loaded_to)

    def _shift_day(delta: int):
        cur = st.session_state.tab2_day
        next_day = cur + timedelta(days=delta)
        if next_day < loaded_from:
            next_day = loaded_from
        if next_day > loaded_to:
            next_day = loaded_to
        st.session_state.tab2_day = next_day

    st.checkbox("1 day step", key="tab2_one_day")
    if st.session_state.tab2_one_day:
        col_prev, col_day, col_next = st.columns([0.6, 1.4, 0.6])
        with col_prev:
            st.button("в—Ђ", key="tab2_prev_day", on_click=_shift_day, args=(-1,))
        with col_day:
            local_day = st.date_input(
                "day",
                value=st.session_state.tab2_day,
                min_value=loaded_from,
                max_value=loaded_to,
                key="tab2_day",
            )
        with col_next:
            st.button("в–¶", key="tab2_next_day", on_click=_shift_day, args=(1,))
        local_from = local_day
        local_to = local_day
    else:
        _range_value = st.date_input(
            "range",
            value=st.session_state.tab2_range_valid,
            min_value=loaded_from,
            max_value=loaded_to,
            key="tab2_range",
        )
        if isinstance(_range_value, tuple) and len(_range_value) == 2:
            local_from, local_to = _range_value
            if local_from < loaded_from:
                local_from = loaded_from
            if local_to > loaded_to:
                local_to = loaded_to
            st.session_state.tab2_range_valid = (local_from, local_to)
        elif isinstance(_range_value, date):
            # in-progress selection: keep last valid range
            local_from, local_to = st.session_state.tab2_range_valid
        else:
            local_from, local_to = st.session_state.tab2_range_valid
    use_local = local_from != loaded_from or local_to != loaded_to
    if local_from > local_to:
        st.warning("Local date range is invalid; using full loaded range.")
        use_local = False

    if use_local:
        if not (ads_daily_by_campaign and by_day_sku):
            st.warning("Local filter needs cached daily data. Press GO to load data.")
            use_local = False

    if use_local:
        base_df = df_campaigns.copy()
        base_df = base_df[base_df["campaign_id"] != "GRAND_TOTAL"].copy()
        sku_map = base_df.set_index("campaign_id")["sku"].astype(str).to_dict()

        def _article_for_items(items):
            vals = []
            for it in items or []:
                sku = str(it.get("sku") or "").strip()
                val = sku_offer_map_for_articles.get(sku, "")
                if not val:
                    val = str(it.get("offer_id") or "").strip()
                if val:
                    vals.append(val)
            vals = list(dict.fromkeys(vals))
            if not vals:
                return ""
            if len(vals) == 1:
                return vals[0]
            return "several"

        rows_filtered = []
        gt_money_spent = 0.0
        gt_views = 0
        gt_clicks = 0
        gt_orders = 0
        gt_revenue = 0.0
        gt_units = 0

        for cid in base_df["campaign_id"].astype(str).tolist():
            items = products_by_campaign_id.get(cid, []) or []
            out_sku, out_title, out_bid, skus = campaign_display_fields("", items)
            article = _article_for_items(items)

            camp_daily = build_campaign_daily_rows_cached(
                campaign_id=str(cid),
                date_from=str(local_from),
                date_to=str(local_to),
                seller_by_day_sku=by_day_sku,
                ads_daily_by_campaign=ads_daily_by_campaign,
                target_drr=target_drr,
                items=items,
            )
            if not camp_daily:
                continue
            df_camp = pd.DataFrame(camp_daily)
            spend = float(pd.to_numeric(df_camp.get("money_spent", 0), errors="coerce").fillna(0).sum())
            views = int(round(float(pd.to_numeric(df_camp.get("views", 0), errors="coerce").fillna(0).sum())))
            clicks = int(round(float(pd.to_numeric(df_camp.get("clicks", 0), errors="coerce").fillna(0).sum())))
            orders = int(round(float(pd.to_numeric(df_camp.get("orders", 0), errors="coerce").fillna(0).sum())))
            revenue = float(pd.to_numeric(df_camp.get("total_revenue", 0), errors="coerce").fillna(0).sum())
            orders_money_ads = float(pd.to_numeric(df_camp.get("orders_money_ads", 0), errors="coerce").fillna(0).sum())
            units = int(round(float(pd.to_numeric(df_camp.get("ordered_units", 0), errors="coerce").fillna(0).sum())))

            click_price = (spend / clicks) if clicks > 0 else 0.0
            ctr_pct = (clicks / views * 100.0) if views > 0 else 0.0
            cr_pct = (units / clicks * 100.0) if clicks > 0 else 0.0
            cpm = (spend / views * 1000.0) if views > 0 else 0.0
            vor_pct = (units / views * 100.0) if views > 0 else 0.0
            vpo = (views / units) if units > 0 else 0.0
            ipo = (views / units) if units > 0 else 0.0
            total_drr_pct = (spend / revenue * 100.0) if revenue > 0 else 0.0

            gt_money_spent += spend
            gt_views += views
            gt_clicks += clicks
            gt_orders += orders
            gt_revenue += revenue
            gt_units += units

            rows_filtered.append(
                {
                    "campaign_id": str(cid),
                    "sku": out_sku if out_sku else sku_map.get(cid, ""),
                    "article": article,
                    "money_spent": spend,
                    "views": views,
                    "clicks": clicks,
                    "click_price": click_price,
                    "cpm": round(cpm, 0),
                    "orders_money_ads": orders_money_ads,
                    "total_revenue": revenue,
                    "ordered_units": units,
                    "total_drr_pct": round(total_drr_pct, 2),
                    "ctr": round(ctr_pct, 1),
                    "cr": round(cr_pct, 1),
                    "ipo": round(ipo, 0),
                    "vor": round(vor_pct, 1),
                    "vpo": round(vpo, 1),
                }
            )

        gt_click_price = (gt_money_spent / gt_clicks) if gt_clicks > 0 else 0.0
        gt_drr_pct = (gt_money_spent / gt_revenue * 100.0) if gt_revenue > 0 else 0.0
        gt_ctr = (gt_clicks / gt_views * 100.0) if gt_views > 0 else 0.0
        gt_cr = (gt_units / gt_clicks * 100.0) if gt_clicks > 0 else 0.0
        gt_ipo = (gt_views / gt_units) if gt_units > 0 else 0.0
        gt_vor = (gt_units / gt_views * 100.0) if gt_views > 0 else 0.0
        gt_vpo = (gt_views / gt_units) if gt_units > 0 else 0.0

        df_campaigns = pd.DataFrame(rows_filtered)
        df_total = pd.DataFrame(
            [
                {
                    "campaign_id": "GRAND_TOTAL",
                    "sku": "",
                    "article": "",
                    "money_spent": gt_money_spent,
                    "views": gt_views,
                    "clicks": gt_clicks,
                    "click_price": round(gt_click_price, 2),
                    "orders_money_ads": "",
                    "total_revenue": gt_revenue,
                    "ordered_units": gt_units,
                    "total_drr_pct": round(gt_drr_pct, 2),
                    "ctr": round(gt_ctr, 1),
                    "cr": round(gt_cr, 1),
                    "ipo": round(gt_ipo, 0),
                    "vor": round(gt_vor, 1),
                    "vpo": round(gt_vpo, 1),
                }
            ]
        )

    st.subheader("Grand total (за период)")
    if not df_total.empty:
        df_total_view = make_view_df(df_total.rename(columns={"total_drr_pct": "total_drr"})).drop(columns=["vor", "rpc", "vpo"], errors="ignore")
        st.dataframe(
            style_median_table(df_total_view, {}, band_pct=BAND_PCT),
            width="stretch",
            hide_index=True,
        )
    else:
        st.warning("GRAND_TOTAL строка не найдена.")

    st.subheader("Кампании (за период)")
    df_campaigns = df_campaigns.copy().drop(columns=["vor", "rpc", "vpo"], errors="ignore")
    def _article_for_campaign_row(r):
        cid = str(r.get("campaign_id"))
        items = products_by_campaign_id.get(cid, []) or []
        vals = []
        for it in items:
            sku = str(it.get("sku") or "").strip()
            val = sku_offer_map_for_articles.get(sku, "")
            if not val:
                val = str(it.get("offer_id") or "").strip()
            if val:
                vals.append(val)
        vals = list(dict.fromkeys(vals))
        if not vals:
            return ""
        if len(vals) == 1:
            return vals[0]
        return "several"

    df_campaigns["article"] = df_campaigns.apply(_article_for_campaign_row, axis=1)
    df_campaigns = df_campaigns.drop(columns=["title"], errors="ignore")
    if "cpm" not in df_campaigns.columns and {"money_spent", "views"}.issubset(df_campaigns.columns):
        _views = pd.to_numeric(df_campaigns["views"], errors="coerce").fillna(0.0)
        _spent = pd.to_numeric(df_campaigns["money_spent"], errors="coerce").fillna(0.0)
        df_campaigns["cpm"] = ((_spent / _views.replace(0, pd.NA)) * 1000.0).fillna(0.0).round(0)
    def _bid_for_row(r):
        cid = str(r.get("campaign_id"))
        items = products_by_campaign_id.get(cid, []) or []
        if not items:
            return ""
        _out_sku, _out_title, out_bid, skus = campaign_display_fields("", items)
        if len(skus) != 1:
            return ""
        return out_bid if out_bid is not None else ""

    df_campaigns["bid"] = df_campaigns.apply(_bid_for_row, axis=1)
    cpc_econ_range_map = st.session_state.get("cpc_econ_range_map") or {}
    cpc_econ_bounds_map = st.session_state.get("cpc_econ_bounds_map") or {}
    if cpc_econ_range_map:
        df_campaigns["cpc_econ_range"] = (
            df_campaigns["campaign_id"].astype(str).map(cpc_econ_range_map).fillna("вЂ”")
        )
    else:
        df_campaigns["cpc_econ_range"] = "?"
    if comments_df is not None and not comments_df.empty:
        period_from = str(local_from if use_local else st.session_state.get("date_from", date_from))
        period_to = str(local_to if use_local else st.session_state.get("date_to", date_to))
        comments_period = comments_df[
            (comments_df["day"] >= period_from) & (comments_df["day"] <= period_to)
        ].copy()
        if not comments_period.empty:
            comments_period = comments_period.sort_values(["day", "ts"], ascending=[False, False])
            comments_all = comments_period[comments_period["campaign_id"].astype(str).str.lower() == "all"]
            comments_campaign = comments_period[comments_period["campaign_id"].astype(str).str.lower() != "all"]
            last_comment_map = (
                comments_campaign.groupby("campaign_id")
                .apply(_combine_comments_with_day)
                .to_dict()
            )
            all_comment = ""
            if not comments_all.empty:
                all_comment = _combine_comments_with_day(comments_all)
        else:
            last_comment_map = {}
            all_comment = ""
    else:
        last_comment_map = {}
        all_comment = ""
    df_campaigns["comment"] = df_campaigns["campaign_id"].astype(str).map(last_comment_map).fillna("")
    df_campaigns["comment_all"] = all_comment if all_comment else ""
    bid_log_df_tab2 = st.session_state.get("bid_log_df")
    if bid_log_df_tab2 is None:
        bid_log_df_tab2 = _load_bid_log_cached()
        st.session_state.bid_log_df = bid_log_df_tab2
    if bid_log_df_tab2 is not None and not bid_log_df_tab2.empty:
        period_from = str(local_from if use_local else st.session_state.get("date_from", date_from))
        period_to = str(local_to if use_local else st.session_state.get("date_to", date_to))
        df_campaigns = add_bid_column_period(
            df_campaigns,
            bid_log_df=bid_log_df_tab2,
            date_from=period_from,
            date_to=period_to,
            campaign_id_col="campaign_id",
            sku_col="sku",
        )
        active_test_map = {}
        test_entries = _list_test_entries(bid_log_df_tab2)
        if not test_entries.empty and "company" in test_entries.columns:
            test_entries = test_entries[
                test_entries["company"].astype(str).isin(["", str(selected_company)])
            ].copy()
        if not test_entries.empty:
            latest_entries = test_entries.sort_values("ts_iso", ascending=False).drop_duplicates(subset=["campaign_id", "sku"], keep="first")
            for _, test_entry in latest_entries.iterrows():
                try:
                    eval_res = _evaluate_test_entry(
                        entry=test_entry,
                        seller_client_id=seller_client_id,
                        seller_api_key=seller_api_key,
                        perf_client_id=perf_client_id,
                        perf_client_secret=perf_client_secret,
                    )
                    if eval_res.get("status") == "active":
                        active_test_map[(str(test_entry.get("campaign_id", "")), str(test_entry.get("sku", "")))] = eval_res
                except Exception:
                    continue
        df_campaigns["Test"] = df_campaigns.apply(
            lambda r: "Да" if (str(r.get("campaign_id", "")), str(r.get("sku", ""))) in active_test_map else "",
            axis=1,
        )
    else:
        df_campaigns["Bid change"] = ""
        df_campaigns["Test"] = ""
    df_campaigns = df_campaigns.rename(
        columns={
            "Изменение bid": "Bid change",
            "РР·РјРµРЅРµРЅРёРµ bid": "Bid change",
            "orders_money_ads": "orders",
            "total_revenue": "revenue",
            "ordered_units": "ordered",
            "total_drr": "drr",
        }
    )
    df_campaigns = df_campaigns.rename(columns={"total_drr_pct": "drr"})
    df_campaigns = df_campaigns.drop(columns=["cpc_econ_range"], errors="ignore")
    ordered_campaign_cols = [
        "campaign_id",
        "sku",
        "article",
        "views",
        "clicks",
        "click_price",
        "money_spent",
        "revenue",
        "drr",
        "orders",
        "ordered",
        "cpm",
        "ctr",
        "cr",
        "ipo",
        "bid",
        "Bid change",
        "Test",
        "comment",
        "comment_all",
    ]
    df_campaigns = df_campaigns[[c for c in ordered_campaign_cols if c in df_campaigns.columns] + [c for c in df_campaigns.columns if c not in ordered_campaign_cols]]
    df_campaigns_view = make_view_df(df_campaigns)
    metrics_campaigns = {
        "money_spent": "lower",
        "clicks": "higher",
        "cpm": "lower",
        "views": "higher",
        "revenue": "higher",
        "drr": "lower",
        "ctr": "higher",
        "cr": "higher",
        "ipo": "lower",
    }
    styler = style_median_table(df_campaigns_view, metrics_campaigns, band_pct=BAND_PCT)
    if cpc_econ_bounds_map and "bid" in df_campaigns_view.columns and "campaign_id" in df_campaigns_view.columns:
        def _bid_outside_econ(frame: pd.DataFrame):
            styled = pd.DataFrame("", index=frame.index, columns=frame.columns)
            for idx in frame.index:
                try:
                    cid = str(frame.at[idx, "campaign_id"])
                except Exception:
                    continue
                bid_raw = df_campaigns.at[idx, "bid"] if "bid" in df_campaigns.columns else None
                try:
                    bid_val = float(bid_raw)
                except Exception:
                    bid_val = None
                if bid_val is None:
                    continue
                bounds = cpc_econ_bounds_map.get(cid)
                if not bounds:
                    continue
                min_v, max_v = bounds
                if min_v is None or max_v is None:
                    continue
                if bid_val > float(max_v):
                    styled.at[idx, "bid"] = "background-color: rgba(255, 230, 128, 0.6);"
            return styled
        styler = styler.apply(_bid_outside_econ, axis=None)

    campaigns_cfg = build_column_config(df_campaigns_view)
    if "orders" in df_campaigns_view.columns:
        campaigns_cfg["orders"] = st.column_config.NumberColumn("orders", format="%.0f")
    if "Bid change" in df_campaigns_view.columns:
        campaigns_cfg["Bid change"] = st.column_config.TextColumn("Bid change", width="small")
    if "comment" in df_campaigns_view.columns:
        campaigns_cfg["comment"] = st.column_config.TextColumn("comment", width="small")
    if "comment_all" in df_campaigns_view.columns:
        campaigns_cfg["comment_all"] = st.column_config.TextColumn("comment_all", width="small")

    st.dataframe(
        styler,
        width="stretch",
        hide_index=True,
        column_config=campaigns_cfg,
    )

if selected_tab == "Current campaigns":
    st.subheader("Детально по кампании")

    running_campaigns_for_pick = fetch_running_campaigns_cached(perf_client_id, perf_client_secret)
    campaign_options = {f'{c.get("title","")} | {c.get("id")}': str(c.get("id")) for c in running_campaigns_for_pick}
    overview_label = "Обзор"

    picked_label = st.selectbox(
        "Кампания",
        options=["(не выбрано)", overview_label] + list(campaign_options.keys()),
        index=0,
        key="campaign_pick",
    )

    picked_campaign_id = None
    if picked_label in campaign_options:
        picked_campaign_id = campaign_options[picked_label]
    else:
        st.session_state.picked_campaign_id = None
        st.session_state.campaign_daily_rows = []

    campaign_daily_rows = st.session_state.get("campaign_daily_rows") or []
    last_loaded_campaign_id = st.session_state.get("picked_campaign_id")
    by_day_sku = st.session_state.get("by_day_sku")
    if picked_label == overview_label:
        st.markdown("### Обзор: DRR по неделям")
        if not by_day_sku or not ads_daily_by_campaign:
            st.info("Сначала нажми GO, чтобы загрузить данные за период.")
        else:
            period_from = str(st.session_state.get("date_from", date_from))
            period_to = str(st.session_state.get("date_to", date_to))
            overview_parts = []
            for camp_label, camp_id in campaign_options.items():
                camp_daily = build_campaign_daily_rows_cached(
                    campaign_id=str(camp_id),
                    date_from=period_from,
                    date_to=period_to,
                    seller_by_day_sku=by_day_sku,
                    ads_daily_by_campaign=ads_daily_by_campaign,
                    target_drr=target_drr,
                    items=products_by_campaign_id.get(str(camp_id), []) or [],
                )
                if not camp_daily:
                    continue
                df_camp_over = pd.DataFrame(camp_daily)
                if df_camp_over.empty:
                    continue
                df_week_over = campaign_weekly_aggregate(df_camp_over, target_drr=target_drr)
                if df_week_over.empty:
                    continue
                rev_over = pd.to_numeric(df_week_over.get("total_revenue", 0), errors="coerce").fillna(0.0)
                drr_over = pd.to_numeric(df_week_over.get("total_drr_pct", 0), errors="coerce").fillna(0.0)
                drr_over = drr_over.where(rev_over > 0, 100.0)
                part = pd.DataFrame(
                    {
                        "week": df_week_over["week"].astype(str),
                        "campaign": camp_label,
                        "drr": drr_over.round(1),
                        "spend": pd.to_numeric(df_week_over.get("money_spent", 0), errors="coerce").fillna(0.0),
                        "revenue": rev_over.round(0),
                    }
                )
                overview_parts.append(part)

            if not overview_parts:
                st.info("Нет данных по выбранному периоду.")
            else:
                df_over = pd.concat(overview_parts, ignore_index=True)
                pivot_drr = df_over.pivot_table(index="campaign", columns="week", values="drr", aggfunc="first")
                pivot_rev = df_over.pivot_table(index="campaign", columns="week", values="revenue", aggfunc="first")
                week_cols_sorted = sorted([c for c in pivot_drr.columns])
                pivot_drr = pivot_drr[week_cols_sorted]
                pivot_rev = pivot_rev.reindex(columns=week_cols_sorted)
                week_labels = format_date_ddmmyyyy(pd.Series(week_cols_sorted)).tolist()
                pivot_drr.columns = week_labels
                pivot_rev.columns = week_labels

                totals = (
                    df_over.groupby("campaign", as_index=False)
                    .agg(total_spend=("spend", "sum"), total_revenue=("revenue", "sum"))
                )
                totals["total_drr"] = totals.apply(
                    lambda r: (r["total_spend"] / r["total_revenue"] * 100.0) if float(r["total_revenue"]) > 0 else 100.0,
                    axis=1,
                )
                totals = totals.set_index("campaign")

                # Build period-level text columns per campaign for overview table.
                def _fmt_bid_micro(micro):
                    try:
                        v = float(micro) / 1_000_000.0
                        if float(v).is_integer():
                            return str(int(v))
                        return f"{v:.2f}".rstrip("0").rstrip(".")
                    except Exception:
                        return "n/a"

                bid_log_df_over = st.session_state.get("bid_log_df")
                if bid_log_df_over is None:
                    bid_log_df_over = _load_bid_log_cached()
                    st.session_state.bid_log_df = bid_log_df_over

                bid_change_map = {}
                if bid_log_df_over is not None and not bid_log_df_over.empty:
                    campaign_ids_set = set(campaign_options.values())
                    bid_src = bid_log_df_over.copy()
                    bid_src["campaign_id"] = bid_src["campaign_id"].astype(str)
                    bid_src = bid_src[bid_src["campaign_id"].isin(campaign_ids_set)]
                    bid_src = bid_src[(bid_src["date"].astype(str) >= period_from) & (bid_src["date"].astype(str) <= period_to)]
                    if not bid_src.empty:
                        bid_src = bid_src.sort_values("ts_iso", ascending=False)
                        for camp_label, camp_id in campaign_options.items():
                            sub = bid_src[bid_src["campaign_id"] == str(camp_id)]
                            if sub.empty:
                                continue
                            ch_items = []
                            seen_ch = set()
                            for _, r in sub.iterrows():
                                d = str(r.get("date", "") or "").strip()
                                old_v = _fmt_bid_micro(r.get("old_bid_micro"))
                                new_v = _fmt_bid_micro(r.get("new_bid_micro"))
                                ch = f"{d}: {old_v} -> {new_v}" if d else f"{old_v} -> {new_v}"
                                cm = str(r.get("comment", "") or "").strip()
                                if cm:
                                    ch = f"{ch}; comment={cm}"
                                if ch and ch not in seen_ch:
                                    seen_ch.add(ch)
                                    ch_items.append(ch)
                            bid_change_map[camp_label] = "\n\n".join(ch_items)

                comment_map = {}
                comment_all_text = ""
                if comments_df is not None and not comments_df.empty:
                    comments_period = comments_df[
                        (comments_df["day"].astype(str) >= period_from) & (comments_df["day"].astype(str) <= period_to)
                    ].copy()
                    if not comments_period.empty:
                        comments_campaign = comments_period[comments_period["campaign_id"].astype(str).str.lower() != "all"]
                        comments_all = comments_period[comments_period["campaign_id"].astype(str).str.lower() == "all"]
                        if not comments_campaign.empty:
                            comments_campaign = comments_campaign.sort_values(["day", "ts"], ascending=[False, False])
                            by_cid = comments_campaign.groupby("campaign_id").apply(_combine_comments_with_day).to_dict()
                            for camp_label, camp_id in campaign_options.items():
                                comment_map[camp_label] = str(by_cid.get(str(camp_id), "") or "").strip()
                        if not comments_all.empty:
                            comment_all_text = _combine_comments_with_day(
                                comments_all.sort_values(["day", "ts"], ascending=[False, False])
                            )

                def _style_drr(x):
                    try:
                        x = float(x)
                    except Exception:
                        return ""
                    if x <= 15:
                        return "background-color: rgba(0, 200, 0, 0.20);"
                    if x <= 25:
                        return ""
                    return "background-color: rgba(255, 0, 0, 0.18);"

                def _fmt_cell(drr_val, rev_val):
                    if pd.isna(drr_val):
                        return ""
                    try:
                        drr_txt = f"{float(drr_val):.1f}"
                    except Exception:
                        drr_txt = str(drr_val)
                    try:
                        rev_txt = f"{int(round(float(rev_val)))}"
                    except Exception:
                        rev_txt = "0"
                    return f"{drr_txt} ({rev_txt})"

                pivot_show = pd.DataFrame(index=pivot_drr.index, columns=pivot_drr.columns)
                for col in pivot_show.columns:
                    pivot_show[col] = [
                        _fmt_cell(drr_v, rev_v)
                        for drr_v, rev_v in zip(pivot_drr[col], pivot_rev[col])
                    ]
                pivot_show.insert(
                    0,
                    "Тотал выручка (период)",
                    [
                        float(totals.at[idx, "total_revenue"]) if idx in totals.index else 0.0
                        for idx in pivot_show.index
                    ],
                )
                pivot_show.insert(
                    0,
                    "Тотал ДРР (период)",
                    [
                        float(totals.at[idx, "total_drr"]) if idx in totals.index else 100.0
                        for idx in pivot_show.index
                    ],
                )
                pivot_show.insert(
                    0,
                    "comment all",
                    [str(comment_all_text or "") for _ in pivot_show.index],
                )
                pivot_show.insert(
                    0,
                    "comment",
                    [str(comment_map.get(idx, "") or "") for idx in pivot_show.index],
                )
                pivot_show.insert(
                    0,
                    "Bid change",
                    [str(bid_change_map.get(idx, "") or "") for idx in pivot_show.index],
                )

                def _style_overview(_frame: pd.DataFrame):
                    styles = pd.DataFrame("", index=_frame.index, columns=_frame.columns)
                    if "Тотал ДРР (период)" in styles.columns:
                        styles["Тотал ДРР (период)"] = [
                            _style_drr(totals.at[idx, "total_drr"]) if idx in totals.index else _style_drr(100.0)
                            for idx in styles.index
                        ]
                    for col in styles.columns:
                        if col in pivot_drr.columns:
                            styles[col] = pivot_drr[col].apply(_style_drr)
                    return styles

                st.dataframe(
                    pivot_show.style.apply(_style_overview, axis=None).format(
                        {
                            "Тотал ДРР (период)": "{:.1f}",
                            "Тотал выручка (период)": "{:.0f}",
                        }
                    ),
                    width="stretch",
                )

    if picked_campaign_id and by_day_sku:
        refresh_detail = st.button("Обновить кампанию")
        if refresh_detail or last_loaded_campaign_id != picked_campaign_id:
            with st.spinner("Загружаю детально по кампании..."):
                campaign_daily_rows = build_campaign_daily_rows_cached(
                    campaign_id=str(picked_campaign_id),
                    date_from=str(st.session_state.get("date_from", date_from)),
                    date_to=str(st.session_state.get("date_to", date_to)),
                    seller_by_day_sku=by_day_sku,
                    ads_daily_by_campaign=ads_daily_by_campaign,
                    target_drr=target_drr,
                    items=products_by_campaign_id.get(str(picked_campaign_id), []) or [],
                )
                st.session_state.campaign_daily_rows = campaign_daily_rows
                st.session_state.picked_campaign_id = picked_campaign_id

    if not picked_campaign_id:
        pass
    elif not by_day_sku:
        st.info("Сначала нажми GO, чтобы загрузить данные за период.")
    elif not campaign_daily_rows:
        st.warning("Нет данных по выбранной кампании за период.")
    else:
        df_camp_daily_raw = pd.DataFrame(campaign_daily_rows)
        bid_log_df = st.session_state.get("bid_log_df")
        if bid_log_df is None:
            bid_log_df = _load_bid_log_cached()
        bid_sku_for_detail = ""
        if "sku" in df_camp_daily_raw.columns:
            unique_skus = (
                df_camp_daily_raw["sku"]
                .astype(str)
                .replace("several", "")
                .replace("None", "")
                .replace("", pd.NA)
                .dropna()
                .unique()
                .tolist()
            )
            if len(unique_skus) == 1:
                bid_sku_for_detail = str(unique_skus[0]).strip()

        spend_sum = float(df_camp_daily_raw["money_spent"].fillna(0).sum())
        views_sum = float(df_camp_daily_raw["views"].fillna(0).sum())
        clicks_sum = float(df_camp_daily_raw["clicks"].fillna(0).sum())
        rev_sum = float(df_camp_daily_raw["total_revenue"].fillna(0).sum())

        ctr_sum = (clicks_sum / views_sum * 100.0) if views_sum > 0 else 0.0
        cpc_sum = (spend_sum / clicks_sum) if clicks_sum > 0 else 0.0
        cpm_sum = (spend_sum / views_sum * 1000.0) if views_sum > 0 else 0.0
        drr_sum = (spend_sum / rev_sum * 100.0) if rev_sum > 0 else 0.0

        def _fetch_current_bid_rub(campaign_id: str, sku: str):
            try:
                token = perf_token(perf_client_id, perf_client_secret)
                products = get_campaign_products_all(token, str(campaign_id), page_size=100)
                for p in products or []:
                    if str(p.get("sku")) != str(sku):
                        continue
                    raw = p.get("bid")
                    if raw is None:
                        raw = p.get("current_bid")
                    if raw is None:
                        return None
                    bid_micro = int(float(str(raw).strip().replace(" ", "").replace(",", ".")))
                    return bid_micro / 1_000_000
            except Exception:
                return None
            return None

        current_bid_rub = None
        if bid_sku_for_detail and picked_campaign_id:
            current_bid_key = f"{picked_campaign_id}:{bid_sku_for_detail}"
            if st.session_state.get("current_bid_key") != current_bid_key:
                with st.spinner("Загружаю текущий bid..."):
                    current_bid_rub = _fetch_current_bid_rub(picked_campaign_id, bid_sku_for_detail)
                st.session_state.current_bid_key = current_bid_key
                st.session_state.current_bid_rub = current_bid_rub
            else:
                current_bid_rub = st.session_state.get("current_bid_rub")

        df_weekly_raw = campaign_weekly_aggregate(df_camp_daily_raw, target_drr=target_drr)
        econ = calc_cpc_econ_only(df_camp_daily_raw, target_drr=target_drr)

        # ----- TOTAL (first) -----
        st.markdown("### Totals (за период)")
        df_total_src = df_camp_daily_raw.copy()
        if "orders" not in df_total_src.columns:
            df_total_src["orders"] = 0
        df_total_src["day"] = pd.to_datetime(df_total_src["day"]).dt.date
        days_in_period = int(df_total_src["day"].nunique()) if "day" in df_total_src.columns else 0
        if days_in_period <= 0:
            days_in_period = 1

        total_money_spent = float(df_total_src["money_spent"].fillna(0).sum())
        total_views = float(df_total_src["views"].fillna(0).sum())
        total_clicks = float(df_total_src["clicks"].fillna(0).sum())
        total_orders = float(df_total_src["orders"].fillna(0).sum())
        total_revenue = float(df_total_src["total_revenue"].fillna(0).sum())
        total_ordered_units = float(df_total_src["ordered_units"].fillna(0).sum())

        total_click_price = (total_money_spent / total_clicks) if total_clicks else 0.0
        total_ctr = (total_clicks / total_views * 100.0) if total_views else 0.0
        total_cr = (total_ordered_units / total_clicks * 100.0) if total_clicks else 0.0
        total_cpm = (total_money_spent / total_views * 1000.0) if total_views else 0.0
        total_drr_pct = (total_money_spent / total_revenue * 100.0) if total_revenue else 0.0
        total_rpc = (total_revenue / total_clicks) if total_clicks else 0.0
        total_target_cpc = total_rpc * target_drr
        total_ipo = (total_views / total_ordered_units) if total_ordered_units else 0.0

        _pf = format_date_ddmmyyyy(pd.Series([st.session_state.get('date_from', date_from)])).iloc[0]
        _pt = format_date_ddmmyyyy(pd.Series([st.session_state.get('date_to', date_to)])).iloc[0]
        period_label = f"{_pf}..{_pt}"
        df_total_period_raw = pd.DataFrame(
            [
                {
                    "week": period_label,
                    "days_in_period": days_in_period,
                    "views": total_views,
                    "clicks": total_clicks,
                    "ctr": round(total_ctr, 1),
                    "cr": round(total_cr, 1),
                    "ipo": round(total_ipo, 0),
                    "money_spent": total_money_spent,
                    "click_price": total_click_price,
                    "cpm": round(total_cpm, 0),
                    "target_cpc": round(total_target_cpc, 1),
                    "total_revenue": total_revenue,
                    "ordered_units": total_ordered_units,
                    "total_drr_pct": round(total_drr_pct, 1),
                }
            ]
        )
        df_total_period = make_view_df(df_total_period_raw).drop(columns=["vor", "rpc", "vpo"], errors="ignore")

        metrics_weekly = {
            "cpm": "lower",
            "views": "higher",
            "total_revenue": "higher",
            "total_drr_pct": "lower",
            "ctr": "higher",
            "cr": "higher",
            "ipo": "lower",
        }

        st.dataframe(
            style_median_table(df_total_period, metrics_weekly, band_pct=BAND_PCT),
            width="stretch",
            hide_index=True,
        )

        st.markdown("### Параметры")
        cpc_econ_range = (
            f"{fmt_rub_1(econ.get('cpc_econ_min')) if econ.get('cpc_econ_min') is not None else 'вЂ”'}"
            f" - {fmt_rub_1(econ.get('cpc_econ')) if econ.get('cpc_econ') is not None else 'вЂ”'}"
            f" - {fmt_rub_1(econ.get('cpc_econ_max')) if econ.get('cpc_econ_max') is not None else 'вЂ”'}"
        )
        lines = [
            f"Текущий bid: {fmt_rub_1(current_bid_rub) if current_bid_rub is not None else '—'}",
            f"CPC econ window: {cpc_econ_range}",
        ]
        st.text("\n".join(lines))

        # ----- WEEKLY (second) -----
        st.markdown("### Детально по кампании (по неделям)")
        df_weekly_raw = add_bid_columns_weekly(
            df_weekly_raw,
            bid_log_df=bid_log_df,
            campaign_id=str(picked_campaign_id),
            sku=bid_sku_for_detail,
        )
        if comments_df is not None and not comments_df.empty:
            camp_comments = comments_df[comments_df["campaign_id"] == str(picked_campaign_id)]
            all_comments = comments_df[comments_df["campaign_id"].astype(str).str.lower() == "all"]
            week_map_campaign = {}
            week_map_all = {}
            if not camp_comments.empty:
                week_map_campaign = (
                    camp_comments.sort_values(["week", "ts"], ascending=[False, False])
                    .groupby("week")["comment"]
                    .apply(_combine_comment_values)
                    .to_dict()
                )
            if not all_comments.empty:
                week_map_all = (
                    all_comments.sort_values(["week", "ts"], ascending=[False, False])
                    .groupby("week")["comment"]
                    .apply(_combine_comment_values)
                    .to_dict()
                )
            if week_map_campaign or week_map_all:
                df_weekly_raw["comment"] = (
                    df_weekly_raw["week"].astype(str).map(lambda w: str(week_map_campaign.get(w, "") or "").strip()).fillna("")
                )
                df_weekly_raw["comment_all"] = (
                    df_weekly_raw["week"].astype(str).map(lambda w: str(week_map_all.get(w, "") or "").strip()).fillna("")
                )
            else:
                df_weekly_raw["comment"] = ""
                df_weekly_raw["comment_all"] = ""
        else:
            df_weekly_raw["comment"] = ""
            df_weekly_raw["comment_all"] = ""
        if "week" in df_weekly_raw.columns:
            df_weekly_raw["week_dt"] = pd.to_datetime(df_weekly_raw["week"], errors="coerce")
            df_weekly_raw = df_weekly_raw.sort_values("week_dt", ascending=False).drop(columns=["week_dt"], errors="ignore")
        df_weekly = make_view_df(df_weekly_raw).drop(columns=["vor", "rpc", "vpo"], errors="ignore")
        if "week" in df_weekly.columns:
            df_weekly["week"] = format_date_ddmmyyyy(df_weekly["week"])

        metrics_weekly = {
            "cpm": "lower",
            "views": "higher",
            "total_revenue": "higher",
            "total_drr_pct": "lower",
            "ctr": "higher",
            "cr": "higher",
            "ipo": "lower",
        }

        st.dataframe(
            style_median_table(df_weekly, metrics_weekly, band_pct=BAND_PCT),
            width="stretch",
            hide_index=True,
        )

        # ----- DAILY (third) -----
        st.markdown("### Детально по кампании (по дням)")
        df_camp_daily_raw_with_bids = add_bid_columns_daily(
            df_camp_daily_raw,
            bid_log_df=bid_log_df,
            campaign_id=str(picked_campaign_id),
            sku=bid_sku_for_detail,
        )
        df_camp_daily_raw_with_bids = df_camp_daily_raw_with_bids.drop(
            columns=["campaign_id", "sku", "rpc", "vpo", "target_cpc", "orders"],
            errors="ignore",
        )
        if comments_df is not None and not comments_df.empty:
            camp_comments = comments_df[comments_df["campaign_id"] == str(picked_campaign_id)]
            all_comments = comments_df[comments_df["campaign_id"].astype(str).str.lower() == "all"]
            day_map_campaign = {}
            day_map_all = {}
            if not camp_comments.empty:
                day_map_campaign = (
                    camp_comments.sort_values(["day", "ts"], ascending=[False, False])
                    .groupby("day")["comment"]
                    .apply(_combine_comment_values)
                    .to_dict()
                )
            if not all_comments.empty:
                day_map_all = (
                    all_comments.sort_values(["day", "ts"], ascending=[False, False])
                    .groupby("day")["comment"]
                    .apply(_combine_comment_values)
                    .to_dict()
                )
            if day_map_campaign or day_map_all:
                df_camp_daily_raw_with_bids["comment"] = (
                    df_camp_daily_raw_with_bids["day"].astype(str).map(lambda d: str(day_map_campaign.get(d, "") or "").strip()).fillna("")
                )
                df_camp_daily_raw_with_bids["comment_all"] = (
                    df_camp_daily_raw_with_bids["day"].astype(str).map(lambda d: str(day_map_all.get(d, "") or "").strip()).fillna("")
                )
            else:
                df_camp_daily_raw_with_bids["comment"] = ""
                df_camp_daily_raw_with_bids["comment_all"] = ""
        else:
            df_camp_daily_raw_with_bids["comment"] = ""
            df_camp_daily_raw_with_bids["comment_all"] = ""
        if "day" in df_camp_daily_raw_with_bids.columns:
            df_camp_daily_raw_with_bids["day_dt"] = pd.to_datetime(df_camp_daily_raw_with_bids["day"], errors="coerce")
            df_camp_daily_raw_with_bids = df_camp_daily_raw_with_bids.sort_values("day_dt", ascending=False).drop(columns=["day_dt"], errors="ignore")
        df_camp_daily = make_view_df(df_camp_daily_raw_with_bids).drop(columns=["vor", "rpc", "vpo"], errors="ignore")
        if "day" in df_camp_daily.columns:
            df_camp_daily["day"] = format_date_ddmmyyyy(df_camp_daily["day"])

        metrics_daily = {
            "cpm": "lower",
            "views": "higher",
            "total_revenue": "higher",
            "total_drr_pct": "lower",
            "ctr": "higher",
            "cr": "higher",
            "ipo": "lower",
        }

        st.dataframe(
            style_median_table(df_camp_daily, metrics_daily, band_pct=BAND_PCT),
            width="stretch",
            hide_index=True,
        )

        # ---- Manual bid control (Phase 1) ----
        col_bid, col_comments = st.columns([2, 1], gap="large")
        with col_bid:
            st.subheader("Управление ставками (ручной тест)")

            if st.session_state.pop("_reset_bid_form", False):
                st.session_state.bid_rub_input = 0.0
                st.session_state.bid_reason_input = "Выбери reason"
                st.session_state.bid_comment_input = ""
                st.session_state.test_target_clicks_input = 0
                st.session_state.test_essence_input = ""
                st.session_state.test_expectations_input = ""

            if "bid_rub_input" not in st.session_state:
                st.session_state.bid_rub_input = 0.0

            if not bid_sku_for_detail:
                st.error("В выбранной кампании несколько SKU. Укажи кампанию с одним SKU.")
            else:
                st.caption(f"SKU: {bid_sku_for_detail}")

                bid_rub = st.number_input("Bid (в‚Ѕ)", min_value=0.0, step=0.5, key="bid_rub_input")
                bid_reason = st.selectbox(
                    "reason",
                    options=["Выбери reason", "Рост продаж", "Снижение остатков", "Снижение ДРР", "Test"],
                    index=0,
                    key="bid_reason_input",
                )
                test_date_from = None
                test_target_clicks = 0
                test_essence = ""
                test_expectations = ""
                if bid_reason == "Test":
                    test_date_from = date.today()
                    test_target_clicks = st.number_input("target_clicks", min_value=1, step=1, key="test_target_clicks_input")
                    test_essence = st.text_input("test_essence", value="", key="test_essence_input")
                    test_expectations = st.text_area("test_expectations", height=80, key="test_expectations_input")
                bid_comment = st.text_input("comment", value="", key="bid_comment_input")
                apply_bid = st.button("APPLY BID", key="apply_bid_btn")

                if apply_bid:
                    if not picked_campaign_id:
                        st.error("Сначала выбери кампанию.")
                    elif bid_reason == "Выбери reason":
                        st.error("Укажи reason.")
                    elif bid_reason == "Test" and (not test_essence.strip() or not test_expectations.strip()):
                        st.error("Для Test заполни суть и ожидания.")
                    elif bid_reason == "Test" and int(test_target_clicks or 0) <= 0:
                        st.error("Для Test укажи target_clicks > 0.")
                    else:
                        campaign_id_for_bid = picked_campaign_id
                        token = perf_token(perf_client_id, perf_client_secret)

                        try:
                            if bid_reason == "Test":
                                full_comment = _build_test_comment_payload(
                                    start_date=str(test_date_from),
                                    target_clicks=int(test_target_clicks),
                                    essence=test_essence,
                                    expectations=test_expectations,
                                    note=bid_comment,
                                    company=selected_company,
                                )
                            else:
                                full_comment = f"reason={bid_reason}; {bid_comment}".strip()
                            result = apply_bid_and_log(
                                token=token,
                                campaign_id=str(campaign_id_for_bid),
                                sku=str(bid_sku_for_detail),
                                bid_rub=float(bid_rub),
                                reason=bid_reason,
                                comment=full_comment,
                                products_loader=get_campaign_products_all,
                                bid_updater=update_campaign_product_bids,
                            )
                            # Refresh cached products to reflect new bid
                            try:
                                updated_items = get_campaign_products_all(
                                    token,
                                    str(campaign_id_for_bid),
                                    page_size=100,
                                )
                                products_by_campaign_id = st.session_state.get("products_by_campaign_id") or {}
                                products_by_campaign_id[str(campaign_id_for_bid)] = updated_items
                                st.session_state.products_by_campaign_id = products_by_campaign_id
                                cache_key = make_ui_state_cache_key(
                                    st.session_state.get("selected_company"),
                                    str(st.session_state.get("date_from", date_from)),
                                    str(st.session_state.get("date_to", date_to)),
                                )
                                cache = normalize_ui_state_cache(load_ui_state_cache(UI_STATE_CACHE_PATH))
                                entry = get_ui_state_entry(cache, cache_key) or {}
                                merged = dict(entry)
                                merged["products_by_campaign_id"] = products_by_campaign_id
                                merged["date_from"] = str(st.session_state.get("date_from", date_from))
                                merged["date_to"] = str(st.session_state.get("date_to", date_to))
                                merged["selected_company"] = st.session_state.get("selected_company")
                                save_ui_state_entry(
                                    UI_STATE_CACHE_PATH,
                                    cache_key,
                                    merged,
                                    selected_company=st.session_state.get("selected_company"),
                                )
                            except Exception:
                                pass
                            st.session_state.last_bid_sku = str(bid_sku_for_detail)
                            st.session_state.last_bid_campaign_id = str(campaign_id_for_bid)
                            st.session_state.current_bid_key = None
                            st.session_state.current_bid_rub = None
                            st.success(
                                f"Р“РѕС‚РѕРІРѕ. РћС‚РїСЂР°РІР»РµРЅРѕ: {bid_rub:.2f} в‚Ѕ "
                                f"(API bid={result.new_bid_micro}, reason={bid_reason})."
                            )
                            by_day_sku = st.session_state.get("by_day_sku")
                            if by_day_sku:
                                with st.spinner("Обновляю кампанию..."):
                                    campaign_daily_rows = build_campaign_daily_rows_cached(
                                        campaign_id=str(campaign_id_for_bid),
                                        date_from=str(st.session_state.get("date_from", date_from)),
                                        date_to=str(st.session_state.get("date_to", date_to)),
                                        seller_by_day_sku=by_day_sku,
                                        ads_daily_by_campaign=st.session_state.get("ads_daily_by_campaign") or {},
                                        target_drr=target_drr,
                                        items=(st.session_state.get("products_by_campaign_id") or {}).get(str(campaign_id_for_bid), []) or [],
                                    )
                                    st.session_state.campaign_daily_rows = campaign_daily_rows
                                    st.session_state.picked_campaign_id = str(campaign_id_for_bid)
                            _load_bid_log_cached.clear()
                            st.session_state.bid_log_df = _load_bid_log_cached()
                            if bid_sku_for_detail and picked_campaign_id:
                                st.session_state.current_bid_key = f"{picked_campaign_id}:{bid_sku_for_detail}"
                                st.session_state.current_bid_rub = float(bid_rub)
                            st.session_state["_reset_bid_form"] = True
                            st.rerun()
                        except Exception as e:
                            logger.exception("Apply bid failed")
                            st.error(f"Ошибка при обновлении bid: {e}")
        with col_comments:
            st.subheader("Комментарии по кампании")
            with st.form("campaign_comment_form", clear_on_submit=True):
                default_comment_day = st.session_state.get("comment_day_input")
                if default_comment_day is None:
                    try:
                        default_comment_day = date.fromisoformat(
                            str(st.session_state.get("date_to", date_to))
                        )
                    except Exception:
                        default_comment_day = date.today()
                comment_day = st.date_input(
                    "Дата изменения",
                    value=default_comment_day,
                    key="comment_day_input",
                )
                comment_all_campaigns = st.checkbox("all campaigns", value=False, key="comment_all_campaigns")
                comment_text = st.text_area("Комментарий", height=120)
                add_comment = st.form_submit_button("Добавить")
            if add_comment:
                if not comment_text.strip():
                    st.error("Нужен текст комментария.")
                elif (not picked_campaign_id) and (not comment_all_campaigns):
                    st.error("Выбери кампанию или отметь all campaigns.")
                else:
                    comment_campaign_id = "all" if comment_all_campaigns else str(picked_campaign_id)
                    append_campaign_comment(
                        path=COMMENTS_PATH,
                        campaign_id=comment_campaign_id,
                        comment=comment_text.strip(),
                        day=comment_day,
                        company=selected_company,
                    )
                    _load_comments_cached.clear()
                    st.success("Комментарий сохранен.")
                    st.rerun()

            if comment_all_campaigns:
                camp_comments = comments_df[comments_df["campaign_id"].astype(str).str.lower() == "all"]
            elif picked_campaign_id:
                camp_comments = comments_df[comments_df["campaign_id"] == str(picked_campaign_id)]
            else:
                camp_comments = pd.DataFrame()

            if camp_comments.empty:
                st.caption("Нет комментариев.")
            else:
                camp_comments_view = camp_comments.sort_values("ts", ascending=False).head(10).copy()
                if "ts" in camp_comments_view.columns:
                    camp_comments_view["ts"] = format_date_ddmmyyyy(camp_comments_view["ts"])
                st.dataframe(
                    camp_comments_view[["day", "ts", "comment"]],
                    width="stretch",
                    hide_index=True,
                )
        st.markdown("### Test parameters")
        latest_test = None
        latest_test_eval = None
        if bid_log_df is not None and bid_sku_for_detail and picked_campaign_id:
            test_entries_for_detail = _list_test_entries(bid_log_df)
            if not test_entries_for_detail.empty and "company" in test_entries_for_detail.columns:
                test_entries_for_detail = test_entries_for_detail[
                    test_entries_for_detail["company"].astype(str).isin(["", str(selected_company)])
                ].copy()
            test_entries_for_detail = test_entries_for_detail[
                (test_entries_for_detail["campaign_id"].astype(str) == str(picked_campaign_id))
                & (test_entries_for_detail["sku"].astype(str) == str(bid_sku_for_detail))
            ].copy()
            if not test_entries_for_detail.empty:
                latest_test_row = test_entries_for_detail.sort_values("ts_iso", ascending=False).iloc[0]
                latest_test = {
                    "start_date": str(latest_test_row.get("start_date", "") or ""),
                    "target_clicks": int(latest_test_row.get("target_clicks", 0) or 0),
                    "essence": str(latest_test_row.get("essence", "") or ""),
                    "expectations": str(latest_test_row.get("expectations", "") or ""),
                    "note": str(latest_test_row.get("note", "") or ""),
                }
                latest_test_eval = _evaluate_test_entry(
                    entry=latest_test_row,
                    seller_client_id=seller_client_id,
                    seller_api_key=seller_api_key,
                    perf_client_id=perf_client_id,
                    perf_client_secret=perf_client_secret,
                )
        if not latest_test:
            st.caption("No test parameters.")
        else:
            test_rows = [
                {"parameter": "status", "value": str((latest_test_eval or {}).get("status", "active")).capitalize()},
                {"parameter": "start_date", "value": latest_test.get("start_date", "")},
                {"parameter": "target_clicks", "value": latest_test.get("target_clicks", 0)},
                {"parameter": "essence", "value": latest_test.get("essence", "")},
                {"parameter": "expectations", "value": latest_test.get("expectations", "")},
            ]
            if (latest_test_eval or {}).get("completion_day"):
                test_rows.append({"parameter": "completion_day", "value": latest_test_eval.get("completion_day", "")})
            if latest_test.get("note"):
                test_rows.append({"parameter": "note", "value": latest_test.get("note", "")})
            st.dataframe(pd.DataFrame(test_rows), width="stretch", hide_index=True)
if selected_tab == "Tests":
    st.subheader("Tests")
    bid_log_df_tests = st.session_state.get("bid_log_df")
    if bid_log_df_tests is None:
        bid_log_df_tests = _load_bid_log_cached()
        st.session_state.bid_log_df = bid_log_df_tests
    tests_df = _list_test_entries(bid_log_df_tests)
    if not tests_df.empty and "company" in tests_df.columns:
        tests_df = tests_df[tests_df["company"].astype(str).isin(["", str(selected_company)])].copy()
    if tests_df.empty:
        st.caption("No tests.")
    else:
        status_filter = st.selectbox("test_status", options=["active", "completed"], index=0, key="tests_status_filter")
        summary_rows = []
        for _, test_entry in tests_df.sort_values("ts_iso", ascending=False).iterrows():
            try:
                eval_res = _evaluate_test_entry(
                    entry=test_entry,
                    seller_client_id=seller_client_id,
                    seller_api_key=seller_api_key,
                    perf_client_id=perf_client_id,
                    perf_client_secret=perf_client_secret,
                )
            except Exception as e:
                logger.exception("Test evaluation failed")
                eval_res = {"status": "active", "completion_day": "", "test_summary": {}, "baseline_summary": {}, "actual_clicks": 0, "error": str(e)}
            if eval_res.get("status") != status_filter:
                continue
            summary_rows.append(
                {
                    "started_at": str(test_entry.get("start_date", "")),
                    "campaign_id": str(test_entry.get("campaign_id", "")),
                    "sku": str(test_entry.get("sku", "")),
                    "target_clicks": int(test_entry.get("target_clicks", 0) or 0),
                    "actual_clicks": int(eval_res.get("actual_clicks", 0) or 0),
                    "status": str(eval_res.get("status", "")),
                    "completion_day": str(eval_res.get("completion_day", "")),
                    "essence": str(test_entry.get("essence", "")),
                    "_entry": test_entry.to_dict(),
                    "_eval": eval_res,
                }
            )
        if not summary_rows:
            st.caption("No tests for selected status.")
        else:
            df_tests_summary = pd.DataFrame([{k: v for k, v in r.items() if not k.startswith("_")} for r in summary_rows])
            st.dataframe(df_tests_summary, width="stretch", hide_index=True)
            if status_filter == "completed":
                st.markdown("### Test results")
                metric_order = ["views", "clicks", "ctr", "cr", "money_spent", "click_price", "total_revenue", "total_drr_pct"]
                for row in summary_rows:
                    st.markdown(f"#### {row['campaign_id']} / {row['sku']} / {row['started_at']}")
                    left, right = st.columns(2)
                    test_summary = row["_eval"].get("test_summary", {}) or {}
                    baseline_summary = row["_eval"].get("baseline_summary", {}) or {}
                    with left:
                        st.caption("Test period")
                        df_test_metrics = make_view_df(pd.DataFrame([test_summary])[metric_order])
                        st.dataframe(df_test_metrics, width="stretch", hide_index=True, column_config=build_column_config(df_test_metrics))
                    with right:
                        st.caption("Previous same-click window")
                        df_prev_metrics = make_view_df(pd.DataFrame([baseline_summary])[metric_order])
                        st.dataframe(df_prev_metrics, width="stretch", hide_index=True, column_config=build_column_config(df_prev_metrics))

if selected_tab == "Formulas":
    render_tab4()

if selected_tab == "Finance balance":
    render_finance_tab(date_from, date_to, seller_client_id=seller_client_id, seller_api_key=seller_api_key, refresh_finance=refresh_finance)

if selected_tab == "Unit Economics":
    render_unit_economics_tab(
        date_from,
        date_to,
        seller_client_id=seller_client_id,
        seller_api_key=seller_api_key,
        company_name=selected_company,
    )

if selected_tab == "Unit Economics Products":
    render_unit_economics_products_tab(
        date_from,
        date_to,
        seller_client_id=seller_client_id,
        seller_api_key=seller_api_key,
        company_name=selected_company,
    )

if selected_tab == "Stocks":
    render_stocks_tab(seller_client_id=seller_client_id, seller_api_key=seller_api_key)

if selected_tab == "Storage":
    render_storage_tab(seller_client_id=seller_client_id, seller_api_key=seller_api_key)

