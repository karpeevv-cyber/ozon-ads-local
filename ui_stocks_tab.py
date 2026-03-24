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


def _load_stocks_settings(*, seller_client_id: str) -> dict[str, int]:
    defaults = {
        "regional_order_min": 2,
        "regional_order_target": 5,
    }
    settings_file = Path(f"stocks_settings_{seller_client_id}.pkl")
    if not settings_file.exists():
        return defaults.copy()
    try:
        with settings_file.open("rb") as f:
            payload = pickle.load(f) or {}
    except Exception:
        return defaults.copy()
    out = defaults.copy()
    for key in out:
        try:
            out[key] = int(payload.get(key, out[key]))
        except Exception:
            pass
    return out


def _stocks_settings_path(*, seller_client_id: str) -> Path:
    return Path(f"stocks_settings_{seller_client_id}.pkl")


def _save_stocks_settings(*, seller_client_id: str, settings: dict[str, int]) -> None:
    settings_file = _stocks_settings_path(seller_client_id=seller_client_id)
    payload = {}
    for key, value in settings.items():
        try:
            payload[key] = int(value)
        except Exception:
            continue
    try:
        with settings_file.open("wb") as f:
            pickle.dump(payload, f)
    except Exception:
        pass


def _is_moscow_or_spb(cluster_name: str) -> bool:
    txt = str(cluster_name or "").strip().lower()
    return any(
        token in txt
        for token in (
            "москва",
            "moscow",
            "санкт-петербург",
            "санкт петербург",
            "петербург",
            "spb",
            "saint petersburg",
            "st petersburg",
        )
    )


def _load_all_product_ids(
    *,
    seller_client_id: str,
    seller_api_key: str,
    visibility: str = "ALL",
) -> list[str]:
    out: list[str] = []
    last_id = ""
    seen_last_ids: set[str] = set()
    max_pages = 1000
    pages = 0
    while True:
        pages += 1
        if pages > max_pages:
            break
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
        next_last_id = str(result.get("last_id", "")) if result.get("last_id") is not None else ""
        if not next_last_id:
            break
        if next_last_id in seen_last_ids:
            # Guard against broken pagination loops where API repeats the same cursor.
            break
        seen_last_ids.add(next_last_id)
        last_id = next_last_id
    # Keep stable order and remove duplicates from repeated pages.
    out = list(dict.fromkeys(out))
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


def _chunks(values: list[str], size: int):
    for i in range(0, len(values), size):
        yield values[i : i + size]


def render_stocks_tab(
    *,
    seller_client_id: str | None,
    seller_api_key: str | None,
) -> None:
    st.subheader("Stocks by warehouse")

    if not seller_client_id or not seller_api_key:
        st.warning("Seller creds are missing for selected company.")
        return

    settings = _load_stocks_settings(seller_client_id=str(seller_client_id))
    if not _stocks_settings_path(seller_client_id=str(seller_client_id)).exists():
        _save_stocks_settings(seller_client_id=str(seller_client_id), settings=settings)
    settings_key = f"stocks:settings:{seller_client_id}"
    if settings_key not in st.session_state:
        st.session_state[settings_key] = settings.copy()

    cache_version = "v2"
    cache_key = f"stocks:{cache_version}:{seller_client_id}"
    ts_key = f"{cache_key}:ts"
    cache_file = Path(f"stocks_cache_{cache_version}_{seller_client_id}.pkl")

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
            sku_batch_size = 200
            for sku_batch in _chunks(skus, sku_batch_size):
                resp = seller_analytics_stocks(
                    skus=sku_batch,
                    client_id=seller_client_id,
                    api_key=seller_api_key,
                )
                items = resp.get("items", []) or []
                if not items:
                    continue
                for it in items:
                    sku = str(it.get("sku") or "")
                    if not sku:
                        continue
                    cluster_id = it.get("cluster_id")
                    cluster_name = it.get("cluster_name") or ""
                    turnover_grade = it.get("turnover_grade_cluster") or it.get("turnover_grade") or ""
                    full_cluster_label = (
                        f"{cluster_id} {cluster_name}".strip()
                        if cluster_id is not None
                        else str(cluster_name).strip()
                    )
                    parts = full_cluster_label.split()
                    cluster_label = parts[1].strip(",.;:") if len(parts) > 1 else full_cluster_label
                    if not cluster_label:
                        cluster_label = "UNKNOWN"
                    rows.append(
                        {
                            "sku": sku,
                            "article": it.get("offer_id") or str(sku),
                            "sku title": it.get("name") or sku_title.get(str(sku), ""),
                            "offer_id": it.get("offer_id") or "",
                            "cluster": cluster_label,
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
        st.caption("As of: вЂ”")

    if not rows:
        sku_count = st.session_state.get(f"{cache_key}:sku_count", 0)
        st.info(f"No data. SKUs checked: {sku_count}.")
        return

    df = pd.DataFrame(rows)
    if df.empty:
        st.info("No data.")
        return
    if "article" not in df.columns:
        if "offer_id" in df.columns:
            df["article"] = df["offer_id"].astype(str)
        else:
            df["article"] = df.get("sku", "").astype(str)
    df["article"] = df["article"].fillna("").astype(str)
    if "sku" in df.columns:
        df.loc[df["article"].str.strip() == "", "article"] = df["sku"].astype(str)
    ui_settings = st.session_state.get(settings_key, {}).copy()
    settings_cols = st.columns(2)
    regional_order_min = int(
        settings_cols[0].number_input(
            "Non-Moscow/SPB lower threshold",
            min_value=0,
            step=1,
            value=int(ui_settings.get("regional_order_min", 2)),
            key=f"{settings_key}:regional_order_min",
        )
    )
    regional_order_target = int(
        settings_cols[1].number_input(
            "Non-Moscow/SPB target",
            min_value=0,
            step=1,
            value=max(int(ui_settings.get("regional_order_target", 5)), regional_order_min),
            key=f"{settings_key}:regional_order_target",
        )
    )
    ui_settings["regional_order_min"] = regional_order_min
    ui_settings["regional_order_target"] = max(regional_order_target, regional_order_min)
    if ui_settings != st.session_state.get(settings_key, {}):
        st.session_state[settings_key] = ui_settings.copy()
        _save_stocks_settings(seller_client_id=str(seller_client_id), settings=ui_settings)

    position_filter = st.selectbox("Position filter", ["ALL", "CORE", "ADDITIONAL"], index=0)
    only_shortages = st.checkbox("Only positions with shortage*", value=False)
    if position_filter != "ALL" and "offer_id" in df.columns:
        is_additional = df["offer_id"].astype(str).str.upper().str.contains("AURA", na=False)
        if position_filter == "ADDITIONAL":
            df = df[is_additional].copy()
        else:
            df = df[~is_additional].copy()
    # shortage filter is applied after aggregation, to avoid partial cluster sums

    if {"article", "cluster", "available_stock_count", "turnover_grade"}.issubset(df.columns):
        transit_days_map = {
            "омск": 20,
            "omsk": 20,
            "уфа": 5,
            "ufa": 5,
            "москва": 5,
            "moscow": 5,
            "санкт-петербург": 5,
            "spb": 5,
            "краснодар": 5,
            "krasnodar": 5,
            "ростов": 5,
            "rostov": 5,
        }
        df_pivot = df.pivot_table(
            index="article",
            columns="cluster",
            values="available_stock_count",
            aggfunc="sum",
        )
        df_ads = df.pivot_table(
            index="article",
            columns="cluster",
            values="ads_cluster",
            aggfunc="mean",
        )
        df_transit = df.pivot_table(
            index="article",
            columns="cluster",
            values="transit_stock_count",
            aggfunc="sum",
        )
        grade_map = df.pivot_table(
            index="article",
            columns="cluster",
            values="turnover_grade",
            aggfunc=lambda s: next((str(x) for x in s if x), ""),
        )
        df_pivot = df_pivot.sort_index()
        df_ads = df_ads.reindex_like(df_pivot)
        df_transit = df_transit.reindex_like(df_pivot)
        grade_map = grade_map.reindex_like(df_pivot)

        # sort clusters by total stock including in-transit (desc)
        cluster_totals = df_pivot.fillna(0).sum(axis=0) + df_transit.fillna(0).sum(axis=0)
        ordered_clusters = (
            cluster_totals.sort_values(ascending=False)
            .index.astype(str)
            .tolist()
        )
        df_pivot = df_pivot.reindex(columns=ordered_clusters)
        df_ads = df_ads.reindex(columns=ordered_clusters)
        df_transit = df_transit.reindex(columns=ordered_clusters)
        grade_map = grade_map.reindex(columns=ordered_clusters)
        # guard against duplicate columns
        df_pivot = df_pivot.loc[:, ~df_pivot.columns.duplicated()]
        df_ads = df_ads.loc[:, ~df_ads.columns.duplicated()]
        df_transit = df_transit.loc[:, ~df_transit.columns.duplicated()]
        grade_map = grade_map.loc[:, ~grade_map.columns.duplicated()]
        stock = df_pivot.fillna(0)
        transit = df_transit.fillna(0)
        total_with_transit = stock + transit
        rule_value = df_ads.fillna(0) * 60.0
        for col in rule_value.columns:
            days = transit_days_map.get(str(col).strip().lower(), 0)
            if days:
                rule_value[col] = rule_value[col] * (1.0 + (days / 60.0))
            if not _is_moscow_or_spb(str(col)):
                rule_value[col] = float(ui_settings.get("regional_order_target", 5))

        if only_shortages:
            shortage_mask = pd.DataFrame(False, index=df_pivot.index, columns=df_pivot.columns)
            for col in shortage_mask.columns:
                if _is_moscow_or_spb(str(col)):
                    shortage_mask[col] = total_with_transit[col] <= rule_value[col]
                else:
                    shortage_mask[col] = total_with_transit[col] <= float(ui_settings.get("regional_order_min", 2))
            eligible_columns = [
                col for col in df_pivot.columns
                if bool((total_with_transit[col] > 10).any() or (transit[col] > 0).any())
            ]
            df_pivot = df_pivot.reindex(columns=eligible_columns)
            df_ads = df_ads.reindex(columns=eligible_columns)
            df_transit = df_transit.reindex(columns=eligible_columns)
            grade_map = grade_map.reindex(columns=eligible_columns)
            stock = stock.reindex(columns=eligible_columns)
            transit = transit.reindex(columns=eligible_columns)
            total_with_transit = total_with_transit.reindex(columns=eligible_columns)
            rule_value = rule_value.reindex(columns=eligible_columns)
            shortage_mask = shortage_mask.reindex(columns=eligible_columns)
            df_pivot = df_pivot.where(shortage_mask)
            df_ads = df_ads.where(shortage_mask)
            df_transit = df_transit.where(shortage_mask)
            grade_map = grade_map.where(shortage_mask)
            if shortage_mask.any(axis=1).any():
                df_pivot = df_pivot[shortage_mask.any(axis=1)]
                df_ads = df_ads.reindex_like(df_pivot)
                df_transit = df_transit.reindex_like(df_pivot)
                grade_map = grade_map.reindex_like(df_pivot)
                rule_value = rule_value.reindex_like(df_pivot)

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
            "**Legend:** "
            "Green = > 28 days. "
            "Light green = 28-56 days. "
            "Blue = 56-120 days. "
            "Pink = 120+ days. "
            "Red = no sales."
        )
        st.caption("Cell format: Stock/Need60/InTransit")
        df_pivot = df_pivot.round(0)
        def _format_cell(val, r, c):
            try:
                base = int(round(float(val)))
            except Exception:
                base = 0
            try:
                ads_val = df_ads.at[r, c]
                ads60 = float(ads_val) * 60.0
                days = transit_days_map.get(str(c).strip().lower(), 0)
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
            return f"{base} | {ads60} | {transit}"

        df_display = df_pivot.copy().astype(object)
        for r in df_display.index:
            for c in df_display.columns:
                if only_shortages and pd.isna(df_display.at[r, c]):
                    df_display.at[r, c] = "вЂ”"
                else:
                    df_display.at[r, c] = _format_cell(df_display.at[r, c], r, c)

        row_h = 35
        header_h = 38
        table_h = header_h + (len(df_display) + 3) * row_h
        st.dataframe(
            df_display.style.apply(_style, axis=None),
            width="stretch",
            height=table_h,
        )
    else:
        row_h = 35
        header_h = 38
        table_h = header_h + (len(df) + 3) * row_h
        st.dataframe(df, width="stretch", hide_index=True, height=table_h)

