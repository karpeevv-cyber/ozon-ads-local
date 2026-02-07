# -*- coding: utf-8 -*-
# ui.py � FULL REPLACEMENT

import streamlit as st
import pandas as pd
from datetime import date

from clients_ads import (
    perf_token,
    get_campaigns,
    update_campaign_product_bids,
)
from clients_seller import seller_analytics_sku_day
from report import build_report_rows, write_csv
from ui_formatting import (
    default_window,
    make_view_df,
    build_column_config,
    fmt_int_space,
    fmt_rub_space,
    fmt_rub_1,
    fmt_pct_1,
    build_download_bytes,
)
from ui_styles import style_median_table, BAND_PCT
from ui_data import (
    rub_to_api_bid_micro,
    fetch_running_campaigns_cached,
    fetch_ads_stats_by_campaign,
    fetch_ads_daily_totals,
    compute_daily_breakdown,
    fetch_products_by_campaign,
    build_campaign_daily_rows,
    campaign_weekly_aggregate,
)
# ---------------- UI ----------------

st.set_page_config(page_title="Ozon Ads — Report UI", layout="wide")
st.title("Ozon Ads — Report UI (MVP)")

# Sidebar
st.sidebar.header("Параметры")
d_from_default, d_to_default = default_window()

date_from = st.sidebar.date_input("date_from", value=d_from_default)
date_to = st.sidebar.date_input("date_to", value=d_to_default)

batch_size = st.sidebar.number_input("Batch size (campaignIds)", min_value=1, max_value=100, value=15, step=1)
include_products = st.sidebar.checkbox("Подгружать товары кампаний (SKU/title/bid)", value=True)

st.sidebar.header("Детально по 1 кампании")
running_campaigns_for_pick = fetch_running_campaigns_cached()
campaign_options = {f'{c.get("title","")} | {c.get("id")}': str(c.get("id")) for c in running_campaigns_for_pick}

picked_label = st.sidebar.selectbox(
    "Кампания",
    options=["(не выбрано)"] + list(campaign_options.keys()),
    index=0,
)

# ---- Manual bid control (Phase 1) ----
st.sidebar.subheader("Управление ставками (ручной тест)")

with st.sidebar.form("bid_form", clear_on_submit=False):
    bid_sku = st.text_input("SKU", value="")
    bid_rub = st.number_input("Bid (₽)", min_value=0.0, value=15.0, step=0.5)
    apply_bid = st.form_submit_button("APPLY BID")

if apply_bid:
    if picked_label == "(не выбрано)":
        st.sidebar.error("Сначала выбери кампанию.")
    elif not bid_sku.strip():
        st.sidebar.error("Укажи SKU.")
    else:
        campaign_id_for_bid = campaign_options[picked_label]
        token = perf_token()

        api_bid = rub_to_api_bid_micro(bid_rub)

        try:
            resp = update_campaign_product_bids(
                token=token,
                campaign_id=str(campaign_id_for_bid),
                bids=[{"sku": str(bid_sku.strip()), "bid": str(api_bid)}],
            )
            _ = resp  # может быть {}
            st.sidebar.success(f"Готово. Отправлено: {bid_rub:.2f} ₽ (API bid={api_bid}).")
        except Exception as e:
            st.sidebar.error(f"Ошибка при обновлении bid: {e}")

# ---- GO button: load data only on explicit click ----
go = st.sidebar.button("GO")

if go:
    with st.spinner("Загружаю данные из Ozon Ads и Seller Analytics..."):
        token = perf_token()

        campaigns = get_campaigns(token)
        running = [c for c in campaigns if c.get("state") == "CAMPAIGN_STATE_RUNNING"]
        running_ids = [str(c["id"]) for c in running]

        # 1) Seller analytics за период: ОДИН вызов (у него cooldown 1 мин)
        by_sku, by_day, by_day_sku = seller_analytics_sku_day(str(date_from), str(date_to), limit=1000)

        # 2) Ads stats за период по всем running campaigns
        stats_by_campaign_id = fetch_ads_stats_by_campaign(token, str(date_from), str(date_to), running_ids, int(batch_size))

        # 3) Products per campaign (если нужно для SKU/title/bid)
        products_by_campaign_id = fetch_products_by_campaign(running, token, include_products)

        # 4) Build report rows (campaigns + GRAND_TOTAL)
        rows_csv, _ = build_report_rows(
            running_campaigns=running,
            stats_by_campaign_id=stats_by_campaign_id,
            sales_map=by_sku,  # sku -> (revenue, units) за период
            products_by_campaign_id=products_by_campaign_id,
        )

        # 5) Ads daily totals + merge with Seller by_day
        ads_daily_rows = fetch_ads_daily_totals(token, str(date_from), str(date_to), running_ids, int(batch_size))
        daily_rows = compute_daily_breakdown(ads_daily_rows, by_day)

        # 6) Campaign daily detail (если выбрана кампания)
        campaign_daily_rows: list[dict] = []
        picked_campaign_id = None
        if picked_label != "(не выбрано)":
            picked_campaign_id = campaign_options[picked_label]
            campaign_daily_rows = build_campaign_daily_rows(
                token=token,
                campaign_id=str(picked_campaign_id),
                date_from=str(date_from),
                date_to=str(date_to),
                seller_by_day_sku=by_day_sku,
            )

        st.session_state.rows_csv = rows_csv
        st.session_state.daily_rows = daily_rows
        st.session_state.campaign_daily_rows = campaign_daily_rows
        st.session_state.picked_campaign_id = picked_campaign_id
        st.session_state.date_from = str(date_from)
        st.session_state.date_to = str(date_to)

# ---------------- Render (no API calls here) ----------------

rows_csv = st.session_state.get("rows_csv")
daily_rows = st.session_state.get("daily_rows")

if not rows_csv:
    st.info("Выбери параметры слева и нажми GO.")
    st.stop()

df = pd.DataFrame(rows_csv)
df_campaigns = df[df["campaign_id"] != "GRAND_TOTAL"].copy()
df_total = df[df["campaign_id"] == "GRAND_TOTAL"].copy()

tab1, tab2, tab3 = st.tabs(
    [
        "Итоги по дням (за период)",
        "Grand total + Кампании (за период)",
        "Детально по кампании",
    ]
)

with tab1:
    st.subheader("Итоги по дням (за период)")
    if daily_rows:
        df_daily = make_view_df(pd.DataFrame(daily_rows))
        st.dataframe(
            df_daily,
            width="stretch",
            hide_index=True,
            column_config=build_column_config(df_daily),
        )
    else:
        st.warning("Нет данных по дням.")

with tab2:
    st.subheader("Grand total (за период)")
    if not df_total.empty:
        df_total_view = make_view_df(df_total)
        st.dataframe(
            df_total_view,
            width="stretch",
            hide_index=True,
            column_config=build_column_config(df_total_view),
        )
    else:
        st.warning("GRAND_TOTAL строка не найдена.")

    st.subheader("Кампании (за период)")
    df_campaigns_view = make_view_df(df_campaigns)
    st.dataframe(
        df_campaigns_view,
        width="stretch",
        hide_index=True,
        column_config=build_column_config(df_campaigns_view),
    )

with tab3:
    st.subheader("Детально по кампании")

    campaign_daily_rows = st.session_state.get("campaign_daily_rows") or []
    picked_campaign_id = st.session_state.get("picked_campaign_id")

    if not picked_campaign_id:
        st.info("Выбери кампанию в сайдбаре и нажми GO.")
    elif not campaign_daily_rows:
        st.warning("Нет данных по выбранной кампании за период.")
    else:
        df_camp_daily_raw = pd.DataFrame(campaign_daily_rows)

        spend_sum = float(df_camp_daily_raw["money_spent"].fillna(0).sum())
        views_sum = float(df_camp_daily_raw["views"].fillna(0).sum())
        clicks_sum = float(df_camp_daily_raw["clicks"].fillna(0).sum())
        rev_sum = float(df_camp_daily_raw["total_revenue"].fillna(0).sum())

        ctr_sum = (clicks_sum / views_sum * 100.0) if views_sum > 0 else 0.0
        cpc_sum = (spend_sum / clicks_sum) if clicks_sum > 0 else 0.0
        cpm_sum = (spend_sum / views_sum * 1000.0) if views_sum > 0 else 0.0
        drr_sum = (spend_sum / rev_sum * 100.0) if rev_sum > 0 else 0.0

        # ----- TOTAL (first) -----
        st.markdown("### Totals (за период)")
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Показы", fmt_int_space(views_sum))
        m2.metric("Клики", fmt_int_space(clicks_sum))
        m3.metric("CTR", fmt_pct_1(ctr_sum))
        m4.metric("Расход", fmt_rub_space(spend_sum))

        m5, m6, m7, m8 = st.columns(4)
        m5.metric("CPC", fmt_rub_1(cpc_sum))
        m6.metric("CPM", fmt_rub_space(cpm_sum))
        m7.metric("Выручка", fmt_rub_space(rev_sum))
        m8.metric("DRR", fmt_pct_1(drr_sum))

        # ----- WEEKLY (second) -----
        st.markdown("### Детально по кампании (по неделям)")
        df_weekly_raw = campaign_weekly_aggregate(df_camp_daily_raw)
        df_weekly = make_view_df(df_weekly_raw)

        metrics_weekly = {
            "cpm": "lower",
            "views": "higher",
            "total_revenue": "higher",
            "total_drr_pct": "lower",
            "ctr": "higher",
        }

        st.dataframe(
            style_median_table(df_weekly, metrics_weekly, band_pct=BAND_PCT),
            width="stretch",
            hide_index=True,
        )

        # ----- DAILY (third) -----
        st.markdown("### Детально по кампании (по дням)")
        df_camp_daily = make_view_df(df_camp_daily_raw)

        metrics_daily = {
            "cpm": "lower",
            "views": "higher",
            "total_revenue": "higher",
            "total_drr_pct": "lower",
            "ctr": "higher",
        }

        st.dataframe(
            style_median_table(df_camp_daily, metrics_daily, band_pct=BAND_PCT),
            width="stretch",
            hide_index=True,
        )

# --- EXPORT (below tabs) ---
st.subheader("Экспорт CSV")
export_name = f"report_{st.session_state.get('date_from', date_from)}_to_{st.session_state.get('date_to', date_to)}.csv"
st.download_button(
    label="Скачать CSV (за период)",
    data=build_download_bytes(df),
    file_name=export_name,
    mime="text/csv",
)

if st.button("Сохранить CSV рядом с проектом"):
    write_csv(df.to_dict("records"), export_name)
    st.success(f"Saved: {export_name}")




