# -*- coding: utf-8 -*-
from __future__ import annotations

from datetime import datetime
from pathlib import Path
import pickle

import pandas as pd
import streamlit as st

from clients_seller import seller_analytics_stocks
from ui_stocks_tab import (
    _chunks,
    _is_moscow_or_spb,
    _load_all_product_ids,
    _load_sku_title_map,
    _load_stocks_settings,
    _save_stocks_settings,
    _stocks_settings_path,
)


def _review_state_path(*, seller_client_id: str) -> Path:
    return Path(f"stocks_review_state_{seller_client_id}.pkl")


def _load_review_state(*, seller_client_id: str) -> dict[str, str]:
    path = _review_state_path(seller_client_id=seller_client_id)
    if not path.exists():
        return {}
    try:
        with path.open("rb") as f:
            payload = pickle.load(f) or {}
    except Exception:
        return {}
    out: dict[str, str] = {}
    for key, value in payload.items():
        status = str(value or "").strip().lower()
        if status in {"pending", "approved", "rejected"}:
            out[str(key)] = status
    return out


def _save_review_state(*, seller_client_id: str, state: dict[str, str]) -> None:
    path = _review_state_path(seller_client_id=seller_client_id)
    payload = {}
    for key, value in state.items():
        status = str(value or "").strip().lower()
        if status in {"pending", "approved", "rejected"}:
            payload[str(key)] = status
    try:
        with path.open("wb") as f:
            pickle.dump(payload, f)
    except Exception:
        pass


def _ensure_stocks_rows(*, seller_client_id: str, seller_api_key: str) -> tuple[list[dict], datetime | None, int]:
    cache_version = "v2"
    cache_key = f"stocks:{cache_version}:{seller_client_id}"
    ts_key = f"{cache_key}:ts"
    cache_file = Path(f"stocks_cache_{cache_version}_{seller_client_id}.pkl")

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

    if cache_key not in st.session_state:
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
            rows: list[dict] = []
            for sku_batch in _chunks(skus, 200):
                resp = seller_analytics_stocks(
                    skus=sku_batch,
                    client_id=seller_client_id,
                    api_key=seller_api_key,
                )
                for it in (resp.get("items", []) or []):
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
            ts = datetime.now()
            st.session_state[cache_key] = rows
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
    return (
        st.session_state.get(cache_key, []),
        st.session_state.get(ts_key),
        int(st.session_state.get(f"{cache_key}:sku_count", 0) or 0),
    )


def _cell_review_key(*, article: str, city: str) -> str:
    return f"{article}|||{city}"


def render_stocks_new_tab(
    *,
    seller_client_id: str | None,
    seller_api_key: str | None,
) -> None:
    st.subheader("Stocks New")

    if not seller_client_id or not seller_api_key:
        st.warning("Seller creds are missing for selected company.")
        return

    settings = _load_stocks_settings(seller_client_id=str(seller_client_id))
    if not _stocks_settings_path(seller_client_id=str(seller_client_id)).exists():
        _save_stocks_settings(seller_client_id=str(seller_client_id), settings=settings)
    settings_key = f"stocks:new:settings:{seller_client_id}"
    if settings_key not in st.session_state:
        st.session_state[settings_key] = settings.copy()

    review_state_key = f"stocks:new:review:{seller_client_id}"
    if review_state_key not in st.session_state:
        st.session_state[review_state_key] = _load_review_state(seller_client_id=str(seller_client_id))

    rows, ts, sku_count = _ensure_stocks_rows(
        seller_client_id=str(seller_client_id),
        seller_api_key=str(seller_api_key),
    )
    if ts:
        st.caption(f"As of: {ts.strftime('%d.%m.%Y %H:%M')}")
    else:
        st.caption("As of: -")

    if not rows:
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
    settings_cols = st.columns(3)
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
    review_mode = settings_cols[2].checkbox(
        "Highlight order candidates",
        value=True,
        key=f"{settings_key}:review_mode",
    )
    ui_settings["regional_order_min"] = regional_order_min
    ui_settings["regional_order_target"] = max(regional_order_target, regional_order_min)
    if ui_settings != st.session_state.get(settings_key, {}):
        st.session_state[settings_key] = ui_settings.copy()
        _save_stocks_settings(seller_client_id=str(seller_client_id), settings=ui_settings)

    position_filter = st.selectbox(
        "Position filter",
        ["ALL", "CORE", "ADDITIONAL"],
        index=0,
        key=f"{settings_key}:position_filter",
    )
    if position_filter != "ALL" and "offer_id" in df.columns:
        is_additional = df["offer_id"].astype(str).str.upper().str.contains("AURA", na=False)
        if position_filter == "ADDITIONAL":
            df = df[is_additional].copy()
        else:
            df = df[~is_additional].copy()

    if not {"article", "cluster", "available_stock_count", "turnover_grade"}.issubset(df.columns):
        st.dataframe(df, width="stretch", hide_index=True)
        return

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

    article_title_map = (
        df.groupby("article")["sku title"].agg(lambda s: next((str(x) for x in s if str(x).strip()), "")).to_dict()
        if "sku title" in df.columns
        else {}
    )

    df_pivot = df.pivot_table(index="article", columns="cluster", values="available_stock_count", aggfunc="sum").sort_index()
    df_ads = df.pivot_table(index="article", columns="cluster", values="ads_cluster", aggfunc="mean").reindex_like(df_pivot)
    df_transit = df.pivot_table(index="article", columns="cluster", values="transit_stock_count", aggfunc="sum").reindex_like(df_pivot)
    grade_map = df.pivot_table(
        index="article",
        columns="cluster",
        values="turnover_grade",
        aggfunc=lambda s: next((str(x) for x in s if x), ""),
    ).reindex_like(df_pivot)

    cluster_totals = df_pivot.fillna(0).sum(axis=0) + df_transit.fillna(0).sum(axis=0)
    ordered_clusters = cluster_totals.sort_values(ascending=False).index.astype(str).tolist()
    df_pivot = df_pivot.reindex(columns=ordered_clusters)
    df_ads = df_ads.reindex(columns=ordered_clusters)
    df_transit = df_transit.reindex(columns=ordered_clusters)
    grade_map = grade_map.reindex(columns=ordered_clusters)
    df_pivot = df_pivot.loc[:, ~df_pivot.columns.duplicated()]
    df_ads = df_ads.loc[:, ~df_ads.columns.duplicated()]
    df_transit = df_transit.loc[:, ~df_transit.columns.duplicated()]
    grade_map = grade_map.loc[:, ~grade_map.columns.duplicated()]

    stock = df_pivot.fillna(0)
    transit = df_transit.fillna(0)
    total_with_transit = stock + transit
    need60 = df_ads.fillna(0) * 60.0
    for col in need60.columns:
        days = transit_days_map.get(str(col).strip().lower(), 0)
        if days:
            need60[col] = need60[col] * (1.0 + (days / 60.0))

    trigger_value = need60.copy()
    target_value = need60.copy()
    candidate_mask = pd.DataFrame(False, index=df_pivot.index, columns=df_pivot.columns)
    eligible_city_mask = pd.DataFrame(False, index=df_pivot.index, columns=df_pivot.columns)
    for col in candidate_mask.columns:
        city_is_eligible = bool((total_with_transit[col] > 10).any() or (transit[col] > 0).any())
        eligible_city_mask[col] = city_is_eligible
        if _is_moscow_or_spb(str(col)):
            candidate_mask[col] = total_with_transit[col] <= need60[col]
            trigger_value[col] = need60[col]
            target_value[col] = need60[col]
        else:
            candidate_mask[col] = total_with_transit[col] <= float(ui_settings.get("regional_order_min", 2))
            trigger_value[col] = float(ui_settings.get("regional_order_min", 2))
            target_value[col] = float(ui_settings.get("regional_order_target", 5))
    candidate_mask = candidate_mask & eligible_city_mask

    review_state = st.session_state.get(review_state_key, {}) or {}
    candidate_rows: list[dict] = []
    for article in df_pivot.index:
        for city in df_pivot.columns:
            if not bool(candidate_mask.at[article, city]):
                continue
            key = _cell_review_key(article=str(article), city=str(city))
            total_now = float(total_with_transit.at[article, city])
            target_now = float(target_value.at[article, city])
            candidate_rows.append(
                {
                    "review_key": key,
                    "article": str(article),
                    "sku title": article_title_map.get(str(article), ""),
                    "city": str(city),
                    "stock": int(round(float(stock.at[article, city]))),
                    "need60": int(round(float(need60.at[article, city]))),
                    "in_transit": int(round(float(transit.at[article, city]))),
                    "total_with_transit": int(round(total_now)),
                    "trigger_value": int(round(float(trigger_value.at[article, city]))),
                    "target_value": int(round(target_now)),
                    "suggested_order": max(0, int(round(target_now - total_now))),
                    "rule_type": "Need60" if _is_moscow_or_spb(str(city)) else "Regional threshold",
                    "status": review_state.get(key, "pending").capitalize(),
                }
            )
    df_candidates = pd.DataFrame(candidate_rows)

    status_map = {"Pending": "#FFE699", "Approved": "#B7E1CD", "Rejected": "#D9D9D9"}
    grade_color_map = {
        "DEFICIT": "#83FFB3",
        "POPULAR": "#D5FFE5",
        "ACTUAL": "#A2D8FF",
        "SURPLUS": "#FFCACA",
        "NO_SALES": "#FF7D7D",
    }

    def _style_matrix(data: pd.DataFrame) -> pd.DataFrame:
        styles = pd.DataFrame("", index=data.index, columns=data.columns)
        for article in data.index:
            for city in data.columns:
                grade = str(grade_map.at[article, city]) if city in grade_map.columns else ""
                color = grade_color_map.get(grade, "")
                if review_mode and bool(candidate_mask.at[article, city]):
                    key = _cell_review_key(article=str(article), city=str(city))
                    status = review_state.get(key, "pending").capitalize()
                    color = status_map.get(status, color)
                    styles.at[article, city] = f"background-color: {color}; font-weight: 700"
                elif color:
                    styles.at[article, city] = f"background-color: {color}"
        return styles

    def _format_cell(article: str, city: str) -> str:
        base = int(round(float(stock.at[article, city])))
        ads60 = int(round(float(need60.at[article, city])))
        transit_val = int(round(float(transit.at[article, city])))
        if review_mode and bool(candidate_mask.at[article, city]):
            key = _cell_review_key(article=str(article), city=str(city))
            status = review_state.get(key, "pending")
            prefix = {"pending": "!", "approved": "+", "rejected": "x"}.get(status, "!")
            return f"{prefix} {base} | {ads60} | {transit_val}"
        return f"{base} | {ads60} | {transit_val}"

    st.markdown(
        "**Legend:** "
        "Pending candidate = yellow. "
        "Approved = green. "
        "Rejected = gray. "
        "Regular turnover colors stay for the rest."
    )
    st.caption("Cell format: Stock/Need60/InTransit")

    df_display = df_pivot.copy().astype(object)
    for article in df_display.index:
        for city in df_display.columns:
            df_display.at[article, city] = _format_cell(str(article), str(city))

    metric_cols = st.columns(4)
    metric_cols[0].metric("Articles", len(df_display.index))
    metric_cols[1].metric("Cities", len(df_display.columns))
    metric_cols[2].metric("Candidates", len(df_candidates))
    metric_cols[3].metric(
        "Approved",
        0 if df_candidates.empty else int((df_candidates["status"] == "Approved").sum()),
    )

    row_h = 35
    header_h = 38
    table_h = min(1200, header_h + (len(df_display) + 3) * row_h)
    st.dataframe(
        df_display.style.apply(_style_matrix, axis=None),
        width="stretch",
        height=table_h,
    )

    st.markdown("### Positions To Review")
    if df_candidates.empty:
        st.caption("No candidates for ordering under current rules.")
        return

    review_filter = st.selectbox(
        "Review status filter",
        ["ALL", "PENDING", "APPROVED", "REJECTED"],
        index=0,
        key=f"{settings_key}:review_filter",
    )
    if review_filter != "ALL":
        df_candidates = df_candidates[df_candidates["status"].str.upper() == review_filter].copy()

    editor_columns = [
        "article",
        "sku title",
        "city",
        "stock",
        "need60",
        "in_transit",
        "total_with_transit",
        "trigger_value",
        "target_value",
        "suggested_order",
        "rule_type",
        "status",
    ]
    edited = st.data_editor(
        df_candidates[["review_key"] + editor_columns],
        width="stretch",
        hide_index=True,
        disabled=[
            "review_key",
            "article",
            "sku title",
            "city",
            "stock",
            "need60",
            "in_transit",
            "total_with_transit",
            "trigger_value",
            "target_value",
            "suggested_order",
            "rule_type",
        ],
        column_config={
            "review_key": None,
            "status": st.column_config.SelectboxColumn(
                "status",
                options=["Pending", "Approved", "Rejected"],
                required=True,
            ),
        },
        key=f"{settings_key}:review_editor",
    )

    updated_state = dict(review_state)
    changed = False
    for row in edited.to_dict("records"):
        key = str(row.get("review_key") or "")
        if not key:
            continue
        new_status = str(row.get("status") or "Pending").strip().lower()
        if new_status not in {"pending", "approved", "rejected"}:
            new_status = "pending"
        if updated_state.get(key, "pending") != new_status:
            updated_state[key] = new_status
            changed = True
    if changed:
        st.session_state[review_state_key] = updated_state
        _save_review_state(seller_client_id=str(seller_client_id), state=updated_state)
        st.rerun()
