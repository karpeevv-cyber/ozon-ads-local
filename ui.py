# -*- coding: utf-8 -*-
# ui.py FULL REPLACEMENT

import streamlit as st
import pandas as pd
import altair as alt
from datetime import date, timedelta
import time
import logging
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
from bid_ui_helpers import (
    apply_bid_and_log,
    add_bid_columns_daily,
    add_bid_columns_weekly,
    load_bid_log_df,
)
from strategy_map import load_strategy_map, upsert_strategy
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

# ---------------- UI ----------------

LOG_PATH = Path("app.log")
logger = logging.getLogger("ozon_ads")
if not logger.handlers:
    logger.setLevel(logging.INFO)
    handler = logging.FileHandler(LOG_PATH, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logger.addHandler(handler)

@st.cache_data(show_spinner=False, ttl=300)
def load_strategy_map_cached() -> pd.DataFrame:
    return load_strategy_map()

st.set_page_config(page_title="Ozon Ads ? Report UI", layout="wide")
st.title("Ozon Ads ? Report UI (MVP)")

UI_STATE_CACHE_PATH = "ui_state_cache.pkl"
COMMENTS_PATH = "campaign_comments.csv"

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

d_from_default, d_to_default = default_window()
_cached_for_dates = normalize_ui_state_cache(load_ui_state_cache(UI_STATE_CACHE_PATH))
_cached_company = _cached_for_dates.get("selected_company")
if _cached_company == selected_company:
    try:
        d_from_default = date.fromisoformat(str(_cached_for_dates.get("date_from", d_from_default)))
    except Exception:
        pass
    try:
        d_to_default = date.fromisoformat(str(_cached_for_dates.get("date_to", d_to_default)))
    except Exception:
        pass

date_from = st.sidebar.date_input("date_from", value=d_from_default)
date_to = st.sidebar.date_input("date_to", value=d_to_default)

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
refresh_stocks = st.sidebar.checkbox("Refresh stocks", value=False)

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
comments_df = load_campaign_comments(COMMENTS_PATH)
data_company = st.session_state.get("data_company")
if data_company and selected_company and data_company != selected_company:
    rows_csv = None
    daily_rows = None

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

tab1, tab2, tab3, tab5, tab6, tab4 = st.tabs(
    [
        "Main",
        "All campaigns",
        "Current campaigns",
        "Finance balance",
        "Stocks",
        "Formulas",
    ]
)

with tab1:
    st.subheader("Итоги по дням (за период)")
    if daily_rows:
        df_daily_raw = pd.DataFrame(daily_rows)
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
            "money_spent",
            "total_drr_pct",
            "views",
            "clicks",
            "ordered_units",
            "cpm",
            "ctr",
            "cr",
            "rpc",
            "vpo",
            "organic_pct",
        ]
        df_daily = df_daily[[c for c in daily_cols if c in df_daily.columns]]
        if "day" in df_daily.columns:
            df_daily["day"] = format_date_ddmmyyyy(df_daily["day"])
        metrics_daily_totals = {
            "cpm": "lower",
            "total_drr_pct": "lower",
            "ctr": "higher",
            "cr": "higher",
            "rpc": "higher",
            "vpo": "lower",
        }
        st.markdown("<div style='height: 20px;'></div>", unsafe_allow_html=True)
        st.dataframe(
            style_median_table(df_daily, metrics_daily_totals, band_pct=BAND_PCT),
            width="stretch",
            hide_index=True,
        )
    else:
        st.warning("Нет данных по дням.")

with tab2:
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
            st.button("◀", key="tab2_prev_day", on_click=_shift_day, args=(-1,))
        with col_day:
            local_day = st.date_input(
                "day",
                value=st.session_state.tab2_day,
                min_value=loaded_from,
                max_value=loaded_to,
                key="tab2_day",
            )
        with col_next:
            st.button("▶", key="tab2_next_day", on_click=_shift_day, args=(1,))
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
        title_map = base_df.set_index("campaign_id")["title"].astype(str).to_dict()
        sku_map = base_df.set_index("campaign_id")["sku"].astype(str).to_dict()
        rows_filtered = []
        gt_money_spent = 0.0
        gt_views = 0
        gt_clicks = 0
        gt_orders = 0
        gt_revenue = 0.0
        gt_units = 0

        for cid in base_df["campaign_id"].astype(str).tolist():
            items = products_by_campaign_id.get(cid, []) or []
            out_sku, out_title, out_bid, skus = campaign_display_fields(title_map.get(cid, ""), items)

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
            vor_pct = (units / views * 100.0) if views > 0 else 0.0
            vpo = (views / units) if units > 0 else 0.0
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
                    "title": out_title,
                    "money_spent": spend,
                    "views": views,
                    "clicks": clicks,
                    "click_price": click_price,
                    "orders_money_ads": orders_money_ads,
                    "total_revenue": revenue,
                    "ordered_units": units,
                    "total_drr_pct": round(total_drr_pct, 2),
                    "ctr": round(ctr_pct, 1),
                    "cr": round(cr_pct, 1),
                    "vor": round(vor_pct, 1),
                    "vpo": round(vpo, 1),
                }
            )

        gt_click_price = (gt_money_spent / gt_clicks) if gt_clicks > 0 else 0.0
        gt_drr_pct = (gt_money_spent / gt_revenue * 100.0) if gt_revenue > 0 else 0.0
        gt_ctr = (gt_clicks / gt_views * 100.0) if gt_views > 0 else 0.0
        gt_cr = (gt_units / gt_clicks * 100.0) if gt_clicks > 0 else 0.0
        gt_vor = (gt_units / gt_views * 100.0) if gt_views > 0 else 0.0
        gt_vpo = (gt_views / gt_units) if gt_units > 0 else 0.0

        df_campaigns = pd.DataFrame(rows_filtered)
        df_total = pd.DataFrame(
            [
                {
                    "campaign_id": "GRAND_TOTAL",
                    "sku": "",
                    "title": "",
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
                    "vor": round(gt_vor, 1),
                    "vpo": round(gt_vpo, 1),
                }
            ]
        )

    st.subheader("Grand total (за период)")
    if not df_total.empty:
        df_total_view = make_view_df(df_total.rename(columns={"total_drr_pct": "total_drr"}))
        st.dataframe(
            style_median_table(df_total_view, {}, band_pct=BAND_PCT),
            width="stretch",
            hide_index=True,
        )
    else:
        st.warning("GRAND_TOTAL строка не найдена.")

    st.subheader("Кампании (за период)")
    df_campaigns = df_campaigns.copy().drop(columns=["vor"], errors="ignore")
    if "strategy" not in df_campaigns.columns:
        strategy_df = load_strategy_map_cached()
        if not strategy_df.empty:
            strategy_df["campaign_id"] = strategy_df["campaign_id"].astype(str)
            strategy_df["sku"] = strategy_df["sku"].astype(str)
            strategy_map = {
                (row["campaign_id"], row["sku"]): str(row.get("strategy_id", "")).strip()
                for _, row in strategy_df.iterrows()
            }
        else:
            strategy_map = {}

        def _strategy_for_row(r):
            sku = str(r.get("sku", "") or "").strip()
            if sku in {"", "None", "several"}:
                return ""
            return strategy_map.get((str(r.get("campaign_id")), sku), "")

        df_campaigns["strategy"] = df_campaigns.apply(_strategy_for_row, axis=1)
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
            df_campaigns["campaign_id"].astype(str).map(cpc_econ_range_map).fillna("—")
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
            comments_period = comments_period.sort_values(["day", "ts"])
            last_comment_map = comments_period.groupby("campaign_id")["comment"].last().to_dict()
        else:
            last_comment_map = {}
    else:
        last_comment_map = {}
    df_campaigns["comment"] = df_campaigns["campaign_id"].astype(str).map(last_comment_map).fillna("")
    if "strategy_df" not in locals():
        strategy_df = load_strategy_map_cached()
    if not strategy_df.empty:
        strategy_df["campaign_id"] = strategy_df["campaign_id"].astype(str)
        strategy_df["updated_date"] = strategy_df["updated_at"].astype(str).str.split("T").str[0]
        updated_map = strategy_df.groupby("campaign_id")["updated_date"].max().to_dict()
        df_campaigns["strategy_updated_at"] = df_campaigns["campaign_id"].astype(str).map(updated_map).fillna("")
    else:
        df_campaigns["strategy_updated_at"] = ""
        updated_map = {}

    by_day_sku = st.session_state.get("by_day_sku")
    if by_day_sku and ads_daily_by_campaign and updated_map:
        drr_after_map: dict[str, float] = {}
        for cid, upd in updated_map.items():
            try:
                upd_date = date.fromisoformat(str(upd))
            except Exception:
                continue
            try:
                period_from = date.fromisoformat(str(local_from if use_local else st.session_state.get("date_from", date_from)))
                period_to = date.fromisoformat(str(local_to if use_local else st.session_state.get("date_to", date_to)))
            except Exception:
                continue
            date_from_eff = max(upd_date, period_from)
            if date_from_eff > period_to:
                continue
            camp_daily = build_campaign_daily_rows_cached(
                campaign_id=str(cid),
                date_from=str(date_from_eff),
                date_to=str(period_to),
                seller_by_day_sku=by_day_sku,
                ads_daily_by_campaign=ads_daily_by_campaign,
                target_drr=target_drr,
                items=products_by_campaign_id.get(str(cid), []) or [],
            )
            if not camp_daily:
                continue
            df_camp = pd.DataFrame(camp_daily)
            spend = float(pd.to_numeric(df_camp.get("money_spent", 0), errors="coerce").fillna(0).sum())
            rev = float(pd.to_numeric(df_camp.get("total_revenue", 0), errors="coerce").fillna(0).sum())
            if rev <= 0:
                continue
            drr_after_map[str(cid)] = round(spend / rev * 100.0, 1)
        df_campaigns["total_drr_after_chng"] = df_campaigns["campaign_id"].astype(str).map(drr_after_map).fillna("")
    else:
        df_campaigns["total_drr_after_chng"] = ""
    df_campaigns = df_campaigns.rename(columns={"total_drr_pct": "total_drr"})
    df_campaigns_view = make_view_df(df_campaigns)
    metrics_campaigns = {
        "views": "higher",
        "total_revenue": "higher",
        "total_drr": "lower",
        "ctr": "higher",
        "cr": "higher",
        "vpo": "lower",
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

    st.dataframe(
        styler,
        width="stretch",
        hide_index=True,
        column_config=build_column_config(df_campaigns_view),
    )

with tab3:
    st.subheader("Детально по кампании")

    running_campaigns_for_pick = fetch_running_campaigns_cached(perf_client_id, perf_client_secret)
    campaign_options = {f'{c.get("title","")} | {c.get("id")}': str(c.get("id")) for c in running_campaigns_for_pick}

    picked_label = st.selectbox(
        "Кампания",
        options=["(не выбрано)"] + list(campaign_options.keys()),
        index=0,
        key="campaign_pick",
    )

    picked_campaign_id = None
    if picked_label != "(не выбрано)":
        picked_campaign_id = campaign_options[picked_label]
    else:
        st.session_state.picked_campaign_id = None
        st.session_state.campaign_daily_rows = []

    campaign_daily_rows = st.session_state.get("campaign_daily_rows") or []
    last_loaded_campaign_id = st.session_state.get("picked_campaign_id")
    by_day_sku = st.session_state.get("by_day_sku")

    if picked_campaign_id and by_day_sku:
        refresh_detail = st.button("Обновить кампанию")
        if refresh_detail or last_loaded_campaign_id != picked_campaign_id:
            with st.spinner("Загружаю деталку кампании..."):
                token = perf_token(perf_client_id, perf_client_secret)
                campaign_daily_rows = build_campaign_daily_rows(
                    token=token,
                    campaign_id=str(picked_campaign_id),
                    date_from=str(st.session_state.get("date_from", date_from)),
                    date_to=str(st.session_state.get("date_to", date_to)),
                    seller_by_day_sku=by_day_sku,
                    target_drr=target_drr,
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
            bid_log_df = load_bid_log_df()
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
                with st.spinner("Р—Р°РіСЂСѓР¶Р°СЋ С‚РµРєСѓС‰РёР№ bid..."):
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
        total_vor = (total_ordered_units / total_views * 100.0) if total_views else 0.0
        total_cpm = (total_money_spent / total_views * 1000.0) if total_views else 0.0
        total_drr_pct = (total_money_spent / total_revenue * 100.0) if total_revenue else 0.0
        total_rpc = (total_revenue / total_clicks) if total_clicks else 0.0
        total_target_cpc = total_rpc * target_drr
        total_vpo = (total_views / total_ordered_units) if total_ordered_units else 0.0

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
                    "vor": round(total_vor, 1),
                    "money_spent": total_money_spent,
                    "click_price": total_click_price,
                    "cpm": round(total_cpm, 0),
                    "rpc": round(total_rpc, 1),
                    "target_cpc": round(total_target_cpc, 1),
                    "vpo": round(total_vpo, 1),
                    "total_revenue": total_revenue,
                    "ordered_units": total_ordered_units,
                    "total_drr_pct": round(total_drr_pct, 1),
                }
            ]
        )
        df_total_period = make_view_df(df_total_period_raw).drop(columns=["vor"], errors="ignore")

        metrics_weekly = {
            "cpm": "lower",
            "views": "higher",
            "total_revenue": "higher",
            "total_drr_pct": "lower",
            "ctr": "higher",
            "cr": "higher",
            "rpc": "higher",
            "vpo": "lower",
        }

        st.dataframe(
            style_median_table(df_total_period, metrics_weekly, band_pct=BAND_PCT),
            width="stretch",
            hide_index=True,
        )

        current_strategy_display = None
        if bid_sku_for_detail and picked_campaign_id:
            _strategy_df = load_strategy_map_cached()
            if not _strategy_df.empty:
                _strategy_df["campaign_id"] = _strategy_df["campaign_id"].astype(str)
                _strategy_df["sku"] = _strategy_df["sku"].astype(str)
                _row = _strategy_df[
                    (_strategy_df["campaign_id"] == str(picked_campaign_id))
                    & (_strategy_df["sku"] == str(bid_sku_for_detail))
                ]
                if not _row.empty:
                    current_strategy_display = str(_row.iloc[0].get("strategy_id", "")).strip() or None
        st.markdown("### Параметры стратегии")
        cpc_econ_range = (
            f"{fmt_rub_1(econ.get('cpc_econ_min')) if econ.get('cpc_econ_min') is not None else '—'}"
            f" - {fmt_rub_1(econ.get('cpc_econ')) if econ.get('cpc_econ') is not None else '—'}"
            f" - {fmt_rub_1(econ.get('cpc_econ_max')) if econ.get('cpc_econ_max') is not None else '—'}"
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
            if not camp_comments.empty:
                week_map = (
                    camp_comments.sort_values(["week", "ts"])
                    .groupby("week")["comment"]
                    .last()
                    .to_dict()
                )
                df_weekly_raw["comment"] = df_weekly_raw["week"].astype(str).map(week_map).fillna("")
            else:
                df_weekly_raw["comment"] = ""
        else:
            df_weekly_raw["comment"] = ""
        if "week" in df_weekly_raw.columns:
            df_weekly_raw["week_dt"] = pd.to_datetime(df_weekly_raw["week"], errors="coerce")
            df_weekly_raw = df_weekly_raw.sort_values("week_dt", ascending=False).drop(columns=["week_dt"], errors="ignore")
        df_weekly = make_view_df(df_weekly_raw).drop(columns=["vor"], errors="ignore")
        if "week" in df_weekly.columns:
            df_weekly["week"] = format_date_ddmmyyyy(df_weekly["week"])

        metrics_weekly = {
            "cpm": "lower",
            "views": "higher",
            "total_revenue": "higher",
            "total_drr_pct": "lower",
            "ctr": "higher",
            "cr": "higher",
            "rpc": "higher",
            "vpo": "lower",
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
            columns=["campaign_id", "sku", "cpm", "rpc", "vpo", "target_cpc", "orders"],
            errors="ignore",
        )
        if comments_df is not None and not comments_df.empty:
            camp_comments = comments_df[comments_df["campaign_id"] == str(picked_campaign_id)]
            if not camp_comments.empty:
                day_map = (
                    camp_comments.sort_values(["day", "ts"])
                    .groupby("day")["comment"]
                    .last()
                    .to_dict()
                )
                df_camp_daily_raw_with_bids["comment"] = (
                    df_camp_daily_raw_with_bids["day"].astype(str).map(day_map).fillna("")
                )
            else:
                df_camp_daily_raw_with_bids["comment"] = ""
        else:
            df_camp_daily_raw_with_bids["comment"] = ""
        if "day" in df_camp_daily_raw_with_bids.columns:
            df_camp_daily_raw_with_bids["day_dt"] = pd.to_datetime(df_camp_daily_raw_with_bids["day"], errors="coerce")
            df_camp_daily_raw_with_bids = df_camp_daily_raw_with_bids.sort_values("day_dt", ascending=False).drop(columns=["day_dt"], errors="ignore")
        df_camp_daily = make_view_df(df_camp_daily_raw_with_bids).drop(columns=["vor"], errors="ignore")
        if "day" in df_camp_daily.columns:
            df_camp_daily["day"] = format_date_ddmmyyyy(df_camp_daily["day"])

        metrics_daily = {
            "cpm": "lower",
            "views": "higher",
            "total_revenue": "higher",
            "total_drr_pct": "lower",
            "ctr": "higher",
            "cr": "higher",
            "rpc": "higher",
            "vpo": "lower",
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

            if st.session_state.get("clear_bid_form"):
                st.session_state.bid_rub_input = 0.0
                st.session_state.bid_reason_input = "Выбери reason"
                st.session_state.bid_comment_input = ""
                st.session_state.clear_bid_form = False
            if "bid_rub_input" not in st.session_state:
                st.session_state.bid_rub_input = 0.0

            if not bid_sku_for_detail:
                st.error("В выбранной кампании несколько SKU. Укажи кампанию с одним SKU.")
            else:
                st.caption(f"SKU: {bid_sku_for_detail}")

                current_strategy = current_strategy_display
                if current_strategy not in {"1", "2", "3"}:
                    current_strategy = "?"

                with st.form("bid_form", clear_on_submit=False):
                    bid_rub = st.number_input("Bid (₽)", min_value=0.0, step=0.5, key="bid_rub_input")
                    bid_reason = st.selectbox(
                        "reason",
                        options=["Выбери reason", "test", "manual change", "strategy"],
                        index=0,
                        key="bid_reason_input",
                    )
                    bid_strategy = st.selectbox(
                        "strategy",
                        options=["?", "1", "2", "3"],
                        index=(["?", "1", "2", "3"].index(current_strategy)),
                        key="bid_strategy_input",
                    )
                    bid_comment = st.text_input("comment", value="", key="bid_comment_input")
                    apply_bid = st.form_submit_button("APPLY BID")

                if apply_bid:
                    if not picked_campaign_id:
                        st.error("Сначала выбери кампанию.")
                    elif bid_reason == "Выбери reason":
                        st.error("Укажи reason.")
                    else:
                        campaign_id_for_bid = picked_campaign_id
                        token = perf_token(perf_client_id, perf_client_secret)

                        try:
                            full_comment = f"reason={bid_reason}; strategy={bid_strategy}; {bid_comment}".strip()
                            upsert_strategy(
                                campaign_id=str(campaign_id_for_bid),
                                sku=str(bid_sku_for_detail),
                                strategy_id=str(bid_strategy),
                                notes=full_comment,
                            )
                            load_strategy_map_cached.clear()
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
                                f"Готово. Отправлено: {bid_rub:.2f} ₽ "
                                f"(API bid={result.new_bid_micro}, reason={bid_reason})."
                            )
                            by_day_sku = st.session_state.get("by_day_sku")
                            if by_day_sku:
                                with st.spinner("Обновляю кампанию..."):
                                    campaign_daily_rows = build_campaign_daily_rows(
                                        token=token,
                                        campaign_id=str(campaign_id_for_bid),
                                        date_from=str(st.session_state.get("date_from", date_from)),
                                        date_to=str(st.session_state.get("date_to", date_to)),
                                        seller_by_day_sku=by_day_sku,
                                        target_drr=target_drr,
                                    )
                                    st.session_state.campaign_daily_rows = campaign_daily_rows
                                    st.session_state.picked_campaign_id = str(campaign_id_for_bid)
                            st.session_state.bid_log_df = load_bid_log_df()
                            st.session_state.clear_bid_form = True
                            st.rerun()
                        except Exception as e:
                            logger.exception("Apply bid failed")
                            st.error(f"Ошибка при обновлении bid: {e}")
        with col_comments:
            st.subheader("Комментарии по кампании")
            if not picked_campaign_id:
                st.info("Выбери кампанию, чтобы оставить комментарий.")
            else:
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
                        "Дата комментария",
                        value=default_comment_day,
                        key="comment_day_input",
                    )
                    comment_text = st.text_area("Комментарий", height=120)
                    add_comment = st.form_submit_button("Добавить")
                if add_comment:
                    if not comment_text.strip():
                        st.error("Нужен текст комментария.")
                    else:
                        append_campaign_comment(
                            path=COMMENTS_PATH,
                            campaign_id=str(picked_campaign_id),
                            comment=comment_text.strip(),
                            day=comment_day,
                        )
                        st.success("Комментарий сохранен.")
                        st.rerun()
                camp_comments = comments_df[comments_df["campaign_id"] == str(picked_campaign_id)]
                if camp_comments.empty:
                    st.caption("Нет комментариев.")
                else:
                    camp_comments_view = camp_comments.sort_values("ts", ascending=False).head(10).copy()
                    if "ts" in camp_comments_view.columns:
                        camp_comments_view["ts"] = format_date_ddmmyyyy(camp_comments_view["ts"])
                    st.dataframe(
                        camp_comments_view[["ts", "comment"]],
                        width="stretch",
                        hide_index=True,
                    )
with tab4:
    render_tab4()

with tab5:
    render_finance_tab(date_from, date_to, seller_client_id=seller_client_id, seller_api_key=seller_api_key, refresh_finance=refresh_finance)

with tab6:
    render_stocks_tab(seller_client_id=seller_client_id, seller_api_key=seller_api_key, refresh_stocks=refresh_stocks)
