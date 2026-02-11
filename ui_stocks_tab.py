# -*- coding: utf-8 -*-
from __future__ import annotations

from datetime import datetime
from pathlib import Path
import pickle

import pandas as pd
import streamlit as st

from clients_seller import (
    seller_product_list,
    seller_product_info_list,
    seller_analytics_stocks,
)


def _load_all_product_ids(
    *,
    seller_client_id: str,
    seller_api_key: str,
    visibility: str = "ALL",
) -> list[str]:
    out: list[str] = []
    last_id = ""
    while True:
        resp = seller_product_list(
            last_id=last_id,
            limit=1000,
            visibility=visibility,
            client_id=seller_client_id,
            api_key=seller_api_key,
        )
        result = resp.get("result", {}) or {}
        items = result.get("items", []) or []
        if not items:
            break
        for it in items:
            pid = it.get("product_id")
            if pid is not None:
                out.append(str(pid))
        last_id = str(result.get("last_id", "")) if result.get("last_id") is not None else ""
        if not last_id:
            break
    return out


def _load_sku_title_map(product_ids: list[str], *, seller_client_id: str, seller_api_key: str) -> dict[str, str]:
    sku_title: dict[str, str] = {}
    chunk = 1000
    for i in range(0, len(product_ids), chunk):
        batch = product_ids[i : i + chunk]
        resp = seller_product_info_list(
            product_ids=batch,
            client_id=seller_client_id,
            api_key=seller_api_key,
        )
        items = resp.get("items", []) or []
        for it in items:
            sku = it.get("sku")
            name = it.get("name") or it.get("offer_id") or ""
            if sku is not None:
                sku_title[str(sku)] = str(name)
    return sku_title


def render_stocks_tab(
    *,
    seller_client_id: str | None,
    seller_api_key: str | None,
) -> None:
    st.subheader("Stocks by warehouse")

    if not seller_client_id or not seller_api_key:
        st.warning("Seller creds are missing for selected company.")
        return

    cache_key = f"stocks:{seller_client_id}"
    ts_key = f"{cache_key}:ts"
    cache_file = Path(f"stocks_cache_{seller_client_id}.pkl")

    refresh_stocks = st.button("Refresh stocks", key=f"{cache_key}:refresh")

    if cache_key not in st.session_state and cache_file.exists():
        try:
            with cache_file.open("rb") as f:
                payload = pickle.load(f) or {}
            st.session_state[cache_key] = payload.get("rows", [])
            st.session_state[ts_key] = payload.get("ts")
            st.session_state[f"{cache_key}:sku_count"] = payload.get("sku_count", 0)
            st.session_state[f"{cache_key}:rows_count"] = payload.get("rows_count", 0)
        except Exception:
            pass

    if refresh_stocks or cache_key not in st.session_state:
        with st.spinner("Loading SKU and stocks..."):
            product_ids = _load_all_product_ids(
                seller_client_id=seller_client_id,
                seller_api_key=seller_api_key,
                visibility="ALL",
            )
            if not product_ids:
                product_ids = _load_all_product_ids(
                    seller_client_id=seller_client_id,
                    seller_api_key=seller_api_key,
                    visibility="VISIBLE",
                )
            sku_title = _load_sku_title_map(
                product_ids,
                seller_client_id=seller_client_id,
                seller_api_key=seller_api_key,
            )
            skus = list(sku_title.keys())
            rows = []
            for sku in skus:
                resp = seller_analytics_stocks(
                    skus=[sku],
                    client_id=seller_client_id,
                    api_key=seller_api_key,
                )
                items = resp.get("items", []) or []
                if not items:
                    continue
                cluster_filter = {
                    147: "Rostov",
                    148: "Ufa",
                    152: "Omsk",
                    154: "MO",
                    17: "Krasnodar",
                    2: "SPB",
                }
                for it in items:
                    cluster_id = it.get("cluster_id")
                    cluster_name = it.get("cluster_name") or ""
                    turnover_grade = it.get("turnover_grade_cluster") or it.get("turnover_grade") or ""
                    if cluster_id not in cluster_filter:
                        continue
                    rows.append(
                        {
                            "sku": sku,
                            "sku title": it.get("name") or sku_title.get(str(sku), ""),
                            "offer_id": it.get("offer_id") or "",
                            "cluster": cluster_filter.get(cluster_id, f"{cluster_id} {cluster_name}").strip(),
                            "turnover_grade": str(turnover_grade),
                            "available_stock_count": float(it.get("available_stock_count", 0) or 0),
                            "ads_cluster": float(it.get("ads_cluster", 0) or 0),
                            "transit_stock_count": float(it.get("transit_stock_count", 0) or 0),
                        }
                    )
            st.session_state[cache_key] = rows
            ts = datetime.now()
            st.session_state[ts_key] = ts
            st.session_state[f"{cache_key}:sku_count"] = len(skus)
            st.session_state[f"{cache_key}:rows_count"] = len(rows)
            try:
                with cache_file.open("wb") as f:
                    pickle.dump(
                        {
                            "rows": rows,
                            "ts": ts,
                            "sku_count": len(skus),
                            "rows_count": len(rows),
                        },
                        f,
                    )
            except Exception:
                pass

    rows = st.session_state.get(cache_key, [])
    ts = st.session_state.get(ts_key)
    if ts:
        st.caption(f"As of: {ts.strftime('%d.%m.%Y %H:%M')}")
    else:
        st.caption("As of: —")

    if not rows:
        sku_count = st.session_state.get(f"{cache_key}:sku_count", 0)
        st.info(f"No data. SKUs checked: {sku_count}.")
        return

    df = pd.DataFrame(rows)
    if df.empty:
        st.info("No data.")
        return
    position_filter = st.selectbox("Position filter", ["ALL", "CORE", "ADDITIONAL"], index=0)
    only_shortages = st.checkbox("Only positions with shortage vs 60-day need", value=False)
    if position_filter != "ALL" and "offer_id" in df.columns:
        is_additional = df["offer_id"].astype(str).str.upper().str.contains("AURA", na=False)
        if position_filter == "ADDITIONAL":
            df = df[is_additional].copy()
        else:
            df = df[~is_additional].copy()
    # shortage filter is applied after aggregation, to avoid partial cluster sums

    if {"sku title", "cluster", "available_stock_count", "turnover_grade"}.issubset(df.columns):
        transit_days_map = {
            "Omsk": 20,
            "Ufa": 5,
            "MO": 5,
            "SPB": 5,
            "Krasnodar": 5,
            "Rostov": 5,
            "Rostov/Krasnodar": 5,
        }
        df_pivot = df.pivot_table(
            index="sku title",
            columns="cluster",
            values="available_stock_count",
            aggfunc="sum",
        )
        df_ads = df.pivot_table(
            index="sku title",
            columns="cluster",
            values="ads_cluster",
            aggfunc="mean",
        )
        df_transit = df.pivot_table(
            index="sku title",
            columns="cluster",
            values="transit_stock_count",
            aggfunc="sum",
        )
        grade_map = df.pivot_table(
            index="sku title",
            columns="cluster",
            values="turnover_grade",
            aggfunc=lambda s: next((str(x) for x in s if x), ""),
        )
        df_pivot = df_pivot.sort_index()
        df_ads = df_ads.reindex_like(df_pivot)
        df_transit = df_transit.reindex_like(df_pivot)
        grade_map = grade_map.reindex_like(df_pivot)

                        # keep stable set/order of clusters
        cluster_order = ["Rostov/Krasnodar", "Ufa", "Omsk", "MO", "SPB"]
        combine_pair = ("Rostov", "Krasnodar")

        # combine Rostov + Krasnodar into one column (before dropping originals)
        if all(c in df_pivot.columns for c in combine_pair):
            df_pivot["Rostov/Krasnodar"] = (
                df_pivot[combine_pair[0]].fillna(0) + df_pivot[combine_pair[1]].fillna(0)
            )
            df_ads["Rostov/Krasnodar"] = (
                df_ads[combine_pair[0]].fillna(0) + df_ads[combine_pair[1]].fillna(0)
            )
            df_transit["Rostov/Krasnodar"] = (
                df_transit[combine_pair[0]].fillna(0) + df_transit[combine_pair[1]].fillna(0)
            )
            # pick worst grade for combined
            grade_order = {"NO_SALES": 0, "DEFICIT": 1, "POPULAR": 2, "ACTUAL": 3, "SURPLUS": 4}

            def _pick_worst(a, b):
                a = str(a) if a is not None else ""
                b = str(b) if b is not None else ""
                if a not in grade_order and b not in grade_order:
                    return ""
                if a not in grade_order:
                    return b
                if b not in grade_order:
                    return a
                return a if grade_order[a] <= grade_order[b] else b

            combined = []
            for r in grade_map.index:
                ga = grade_map.at[r, combine_pair[0]]
                gb = grade_map.at[r, combine_pair[1]]
                combined.append(_pick_worst(ga, gb))
            grade_map["Rostov/Krasnodar"] = combined

        # ensure final order (drop originals)
        df_pivot = df_pivot.reindex(columns=cluster_order)
        df_ads = df_ads.reindex(columns=cluster_order)
        df_transit = df_transit.reindex(columns=cluster_order)
        grade_map = grade_map.reindex(columns=cluster_order)
        # guard against duplicate columns
        df_pivot = df_pivot.loc[:, ~df_pivot.columns.duplicated()]
        df_ads = df_ads.loc[:, ~df_ads.columns.duplicated()]
        df_transit = df_transit.loc[:, ~df_transit.columns.duplicated()]
        grade_map = grade_map.loc[:, ~grade_map.columns.duplicated()]

        if only_shortages:
            need60 = df_ads.fillna(0) * 60.0
            for col in need60.columns:
                days = transit_days_map.get(col, 0)
                if days:
                    need60[col] = need60[col] * (1.0 + (days / 60.0))
            stock = df_pivot.fillna(0)
            shortage_mask = (stock < need60) | (stock <= 2)
            df_pivot = df_pivot.where(shortage_mask)
            df_ads = df_ads.where(shortage_mask)
            df_transit = df_transit.where(shortage_mask)
            grade_map = grade_map.where(shortage_mask)
            if shortage_mask.any(axis=1).any():
                df_pivot = df_pivot[shortage_mask.any(axis=1)]
                df_ads = df_ads.reindex_like(df_pivot)
                df_transit = df_transit.reindex_like(df_pivot)
                grade_map = grade_map.reindex_like(df_pivot)

        color_map = {
            "DEFICIT": "#83FFB3",   # green
            "POPULAR": "#D5FFE5",   # light green
            "ACTUAL": "#A2D8FF",    # blue
            "SURPLUS": "#FFCACA",   # pink
            "NO_SALES": "#FF7D7D",  # red
        }

        def _style(data):
            styles = pd.DataFrame("", index=data.index, columns=data.columns)
            for r in data.index:
                for c in data.columns:
                    grade = str(grade_map.at[r, c]) if c in grade_map.columns else ""
                    color = color_map.get(grade, "")
                    if color:
                        styles.at[r, c] = f"background-color: {color}"
            return styles

        st.markdown(
            "**Легенда:** "
            "Зеленый — > 28 дней. "
            "Светло зеленый — 28–56 дней. "
            "Синий — 56–120 дней. "
            "Розовый — 120+ дней. "
            "Красный — не было продаж."
        )
        df_pivot = df_pivot.round(0)
        def _format_cell(val, r, c):
            try:
                base = int(round(float(val)))
            except Exception:
                base = 0
            try:
                ads_val = df_ads.at[r, c]
                ads60 = float(ads_val) * 60.0
                days = transit_days_map.get(c, 0)
                if days:
                    ads60 = ads60 * (1.0 + (days / 60.0))
                ads60 = int(round(ads60))
            except Exception:
                ads60 = 0
            try:
                transit_val = df_transit.at[r, c]
                transit = int(round(float(transit_val)))
            except Exception:
                transit = 0
            return f"{base} ({ads60}/{transit})"

        df_display = df_pivot.copy().astype(object)
        for r in df_display.index:
            for c in df_display.columns:
                if only_shortages and pd.isna(df_display.at[r, c]):
                    df_display.at[r, c] = "—"
                else:
                    df_display.at[r, c] = _format_cell(df_display.at[r, c], r, c)

        st.dataframe(
            df_display.style.apply(_style, axis=None),
            width="stretch",
        )
    else:
        st.dataframe(df, width="stretch", hide_index=True)

