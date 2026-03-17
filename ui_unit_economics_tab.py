# -*- coding: utf-8 -*-
from __future__ import annotations

from datetime import date
from io import StringIO

import pandas as pd
import requests
import streamlit as st

from clients_seller import seller_analytics_data, seller_finance_balance


UNIT_ECON_SHEETS = {
    "Osome tea": {"sheet_id": "17W18g8mCD2VxtNIOr8EaVM4Hik4cLI444HeFWx31-Ts", "gid": "703239472"},
    "Aura tea": {"sheet_id": "1DdBm9Ul__fyUY0hWobwg1fTtIzmILif4ycV_1503R8g", "gid": "703239472"},
}

SHEET_TEA_COST = "\u0441\u0435\u0431\u0435\u0441 \u043f\u043e\u0440\u0446\u0438\u0438 \u0447\u0430\u044f"
SHEET_PACKAGE_COST = "\u043a\u043e\u0441\u0442\u044b \u0443\u043f"
SHEET_PACKAGE_COST_ALT = "\u043a\u043e\u0441\u0442\u044b \u0443\u043f\u0430\u043a\u043e\u0432\u043a\u0438"
SHEET_LABEL_COST = "\u044d\u0442\u0438\u043a\u0435\u0442\u043a\u0438"
SHEET_LABEL_COST_ALT = "\u043a\u043e\u0441\u0442\u044b \u044d\u0442\u0438\u043a\u0435\u0442\u043a\u0438"
SHEET_PACKING_COST = "\u0444\u0430\u0441\u043e\u0432\u043a\u0430"
SHEET_PACKING_COST_ALT = "\u043a\u043e\u0441\u0442\u044b \u0444\u0430\u0441\u043e\u0432\u043a\u0438"


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


def _sheet_csv_url(sheet_id: str, gid: str) -> str:
    return f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv&gid={gid}"


def get_unit_econ_sheet_config(company_name: str | None) -> dict[str, str] | None:
    if not company_name:
        return None
    return UNIT_ECON_SHEETS.get(str(company_name).strip())


def get_unit_econ_products_path(company_name: str | None) -> str:
    safe = (str(company_name or "").strip().lower().replace(" ", "_")) or "default"
    return f"unit_economics_products_{safe}.csv"


@st.cache_data(show_spinner=False, ttl=60)
def _load_unit_cost_overrides(path: str) -> pd.DataFrame:
    try:
        df = pd.read_csv(path, dtype={"sku": str})
    except Exception:
        return pd.DataFrame(columns=["sku", "position", "tea_cost", "package_cost", "label_cost", "packing_cost"])
    for col in ["sku", "position", "tea_cost", "package_cost", "label_cost", "packing_cost"]:
        if col not in df.columns:
            df[col] = ""
    df["sku"] = df["sku"].astype(str).str.strip()
    df = df[df["sku"].str.fullmatch(r"\d+")].copy()
    return df[["sku", "position", "tea_cost", "package_cost", "label_cost", "packing_cost"]]


def save_unit_cost_overrides(df: pd.DataFrame, path: str) -> None:
    out = df.copy()
    out["sku"] = out["sku"].astype(str).str.strip()
    out = out[out["sku"].str.fullmatch(r"\d+")].copy()
    out.to_csv(path, index=False, encoding="utf-8-sig")
    _load_unit_cost_overrides.clear()
    load_effective_unit_costs.clear()
    load_unit_economics_daily_summary.clear()
    load_unit_economics_day_table.clear()
    load_unit_economics_sku_period_summary.clear()


def _normalize_header(text: str) -> str:
    return str(text or "").strip().lower().replace("ё", "е").replace("\xa0", " ").replace("_", " ")


@st.cache_data(show_spinner=False, ttl=1800)
def _load_unit_costs(sheet_id: str, gid: str) -> pd.DataFrame:
    resp = requests.get(_sheet_csv_url(sheet_id, gid), timeout=30)
    resp.raise_for_status()
    raw = pd.read_csv(StringIO(resp.content.decode("utf-8-sig", errors="replace")), header=None, dtype=str).fillna("")
    if raw.shape[0] < 3:
        return pd.DataFrame(columns=["sku", "sheet_name", "tea_cost", "package_cost", "label_cost", "packing_cost"])

    data = raw.iloc[2:].copy()
    data.columns = [_normalize_header(x) for x in raw.iloc[1].tolist()]
    sku_col = "sku" if "sku" in data.columns else data.columns[0]
    data["sku"] = data[sku_col].astype(str).str.strip()
    data = data[data["sku"].str.fullmatch(r"\d+")].copy()
    if data.empty:
        return pd.DataFrame(columns=["sku", "sheet_name", "tea_cost", "package_cost", "label_cost", "packing_cost"])

    empty_series = pd.Series([""] * len(data), index=data.index, dtype=str)
    name_part_1 = data.iloc[:, 1].astype(str).str.strip() if data.shape[1] > 1 else empty_series
    name_part_2 = data.iloc[:, 2].astype(str).str.strip() if data.shape[1] > 2 else empty_series

    def pick(*names: str) -> pd.Series:
        for name in names:
            if name in data.columns:
                return data[name]
        return empty_series

    return pd.DataFrame(
        {
            "sku": data["sku"].astype(str),
            "sheet_name": (name_part_1.fillna("") + " " + name_part_2.fillna("")).str.strip(),
            "tea_cost": pick(SHEET_TEA_COST).apply(_to_num),
            "package_cost": pick(SHEET_PACKAGE_COST, SHEET_PACKAGE_COST_ALT).apply(_to_num),
            "label_cost": pick(SHEET_LABEL_COST, SHEET_LABEL_COST_ALT).apply(_to_num),
            "packing_cost": pick(SHEET_PACKING_COST, SHEET_PACKING_COST_ALT).apply(_to_num),
        }
    )


@st.cache_data(show_spinner=False, ttl=300)
def load_effective_unit_costs(company_name: str | None) -> pd.DataFrame:
    cfg = get_unit_econ_sheet_config(company_name)
    if not cfg:
        return pd.DataFrame(columns=["sku", "sheet_name", "tea_cost", "package_cost", "label_cost", "packing_cost"])
    base = _load_unit_costs(cfg["sheet_id"], cfg["gid"]).copy()
    overrides = _load_unit_cost_overrides(get_unit_econ_products_path(company_name)).copy()
    if overrides.empty:
        return base
    overrides["position"] = overrides["position"].astype(str).fillna("").str.strip()
    for col in ["tea_cost", "package_cost", "label_cost", "packing_cost"]:
        overrides[col] = pd.to_numeric(overrides[col], errors="coerce")
    merged = base.merge(overrides, on="sku", how="outer", suffixes=("", "__override"))
    merged["sheet_name"] = merged.get("position", "").where(
        merged.get("position", "").astype(str).str.strip().ne(""),
        merged.get("sheet_name", "").astype(str),
    )
    for col in ["tea_cost", "package_cost", "label_cost", "packing_cost"]:
        override_col = f"{col}__override"
        if override_col in merged.columns:
            merged[col] = merged[override_col].where(merged[override_col].notna(), merged[col])
    return merged[["sku", "sheet_name", "tea_cost", "package_cost", "label_cost", "packing_cost"]].copy()


@st.cache_data(show_spinner=False, ttl=900)
def _load_sales_by_sku_day_rows(date_from: str, date_to: str, *, seller_client_id: str | None, seller_api_key: str | None) -> pd.DataFrame:
    rows: list[dict] = []
    offset = 0
    limit = 1000
    while True:
        payload = seller_analytics_data(
            date_from=date_from,
            date_to=date_to,
            dimension=["sku", "day"],
            metrics=["revenue", "ordered_units"],
            limit=limit,
            offset=offset,
            client_id=seller_client_id,
            api_key=seller_api_key,
        )
        data = (payload.get("result", {}) or {}).get("data", []) or []
        if not data:
            break
        for item in data:
            dims = item.get("dimensions", []) or []
            metrics = item.get("metrics", []) or []
            rows.append(
                {
                    "sku": str((dims[0] or {}).get("id", "")).strip() if len(dims) > 0 else "",
                    "name": str((dims[0] or {}).get("name", "")).strip() if len(dims) > 0 else "",
                    "day": str((dims[1] or {}).get("id", "")).strip() if len(dims) > 1 else "",
                    "revenue": _to_num(metrics[0] if len(metrics) > 0 else 0),
                    "ordered_units": int(round(_to_num(metrics[1] if len(metrics) > 1 else 0))),
                }
            )
        if len(data) < limit:
            break
        offset += limit
    df = pd.DataFrame(rows)
    if df.empty:
        return pd.DataFrame(columns=["sku", "name", "day", "revenue", "ordered_units"])
    return df[df["sku"].astype(str).str.strip().ne("")].copy()


@st.cache_data(show_spinner=False, ttl=900)
def _load_sales_by_sku(date_from: str, date_to: str, *, seller_client_id: str | None, seller_api_key: str | None) -> pd.DataFrame:
    df = _load_sales_by_sku_day_rows(date_from, date_to, seller_client_id=seller_client_id, seller_api_key=seller_api_key)
    if df.empty:
        return pd.DataFrame(columns=["sku", "name", "quantity", "revenue", "sale"])
    grouped = df.groupby("sku", as_index=False).agg(quantity=("ordered_units", "sum"), revenue=("revenue", "sum"), name=("name", "first"))
    grouped = grouped[grouped["quantity"] > 0].copy()
    grouped["sale"] = grouped.apply(lambda r: float(r["revenue"]) / float(r["quantity"]) if float(r["quantity"]) > 0 else 0.0, axis=1)
    return grouped


@st.cache_data(show_spinner=False, ttl=900)
def _load_finance_period_costs(date_from: str, date_to: str, *, seller_client_id: str | None, seller_api_key: str | None) -> dict[str, float]:
    payload = seller_finance_balance(date_from=date_from, date_to=date_to, client_id=seller_client_id, api_key=seller_api_key)
    services = ((payload.get("cashflows", {}) or {}).get("services", [])) or []
    out = {
        "logistics": 0.0,
        "cross_docking": 0.0,
        "acceptance": 0.0,
        "marketing": 0.0,
        "promotion_with_cpo": 0.0,
        "acquiring": 0.0,
        "reverse_logistics": 0.0,
        "returns_processing": 0.0,
        "errors": 0.0,
        "storage": 0.0,
        "points_for_reviews": 0.0,
        "seller_bonuses": 0.0,
    }
    for service in services:
        name = str(service.get("name", "") or "").strip()
        value = abs(_to_num((service.get("amount", {}) or {}).get("value", 0)))
        if name in {"logistics", "courier_client_reinvoice"}:
            out["logistics"] += value
        elif name == "cross_docking":
            out["cross_docking"] += value
        elif name == "goods_processing_in_shipment":
            out["acceptance"] += value
        elif name == "pay_per_click":
            out["marketing"] += value
        elif name == "promotion_with_cost_per_order":
            out["promotion_with_cpo"] += value
        elif name == "acquiring":
            out["acquiring"] += value
        elif name == "reverse_logistics":
            out["reverse_logistics"] += value
        elif name == "partner_returns_cancellations_processing":
            out["returns_processing"] += value
        elif name == "booking_space_and_staff_for_partial_shipment":
            out["errors"] += value
        elif name == "product_placement_in_ozon_warehouses":
            out["storage"] += value
        elif name == "points_for_reviews":
            out["points_for_reviews"] += value
        elif name == "seller_bonuses":
            out["seller_bonuses"] += value
    return out


def _apply_unit_econ_costs(sales_df: pd.DataFrame, costs_df: pd.DataFrame, finance_costs: dict[str, float]) -> pd.DataFrame:
    if sales_df.empty:
        return pd.DataFrame()
    total_units = float(pd.to_numeric(sales_df["quantity"], errors="coerce").fillna(0).sum())
    if total_units <= 0:
        return pd.DataFrame()
    merged = sales_df.merge(costs_df, on="sku", how="left")
    merged["position"] = merged["name"].astype(str).str.strip()
    missing_name = merged["position"].eq("")
    merged.loc[missing_name, "position"] = merged.loc[missing_name, "sheet_name"].astype(str).str.strip()
    for col in ["tea_cost", "package_cost", "label_cost", "packing_cost"]:
        merged[col] = pd.to_numeric(merged[col], errors="coerce").fillna(0.0)
    merged["delivery_fbo"] = (finance_costs["cross_docking"] + finance_costs["acceptance"]) / total_units
    merged["promotion"] = (finance_costs["marketing"] + finance_costs["promotion_with_cpo"]) / total_units
    merged["ozon_percent_cost"] = merged["sale"].apply(lambda x: float(x) * (0.20 if float(x) <= 300 else 0.31))
    merged["ozon_logistics"] = finance_costs["logistics"] / total_units
    merged["other_costs"] = (
        finance_costs["acquiring"] + finance_costs["reverse_logistics"] + finance_costs["returns_processing"] + finance_costs["errors"] + finance_costs["storage"]
    ) / total_units
    merged["review_points"] = finance_costs["points_for_reviews"] / total_units
    merged["seller_bonuses"] = finance_costs["seller_bonuses"] / total_units
    merged["taxes"] = merged["sale"].astype(float) * 0.025
    merged["EBITDA"] = (
        merged["sale"].astype(float)
        - merged["tea_cost"] - merged["package_cost"] - merged["label_cost"] - merged["packing_cost"]
        - merged["delivery_fbo"] - merged["promotion"] - merged["ozon_percent_cost"] - merged["ozon_logistics"]
        - merged["other_costs"] - merged["review_points"] - merged["seller_bonuses"] - merged["taxes"]
    )
    merged["ebitda_pct"] = merged.apply(lambda r: (float(r["EBITDA"]) / float(r["sale"]) * 100.0) if float(r["sale"]) else 0.0, axis=1)
    return merged


def _build_day_sales(raw_sales_df: pd.DataFrame) -> pd.DataFrame:
    if raw_sales_df.empty:
        return pd.DataFrame()
    day_sales_df = raw_sales_df.groupby(["day", "sku"], as_index=False).agg(quantity=("ordered_units", "sum"), revenue=("revenue", "sum"), name=("name", "first"))
    day_sales_df = day_sales_df[day_sales_df["quantity"] > 0].copy()
    if day_sales_df.empty:
        return pd.DataFrame()
    day_sales_df["sale"] = day_sales_df.apply(lambda r: float(r["revenue"]) / float(r["quantity"]) if float(r["quantity"]) > 0 else 0.0, axis=1)
    return day_sales_df


@st.cache_data(show_spinner=False, ttl=900)
def load_unit_economics_daily_summary(date_from: str, date_to: str, *, seller_client_id: str | None, seller_api_key: str | None, company_name: str | None) -> pd.DataFrame:
    costs_df = load_effective_unit_costs(company_name)
    raw_sales_df = _load_sales_by_sku_day_rows(date_from, date_to, seller_client_id=seller_client_id, seller_api_key=seller_api_key)
    day_sales_df = _build_day_sales(raw_sales_df)
    if costs_df.empty or day_sales_df.empty:
        return pd.DataFrame(columns=["day", "ebitda", "ebitda_pct"])
    parts: list[pd.DataFrame] = []
    for day_str in sorted(day_sales_df["day"].astype(str).unique().tolist()):
        sales_day = day_sales_df[day_sales_df["day"].astype(str) == str(day_str)].copy()
        finance_costs = _load_finance_period_costs(str(day_str), str(day_str), seller_client_id=seller_client_id, seller_api_key=seller_api_key)
        applied = _apply_unit_econ_costs(sales_day, costs_df, finance_costs)
        if applied.empty:
            continue
        applied["day"] = str(day_str)
        parts.append(applied)
    if not parts:
        return pd.DataFrame(columns=["day", "ebitda", "ebitda_pct"])
    full_df = pd.concat(parts, ignore_index=True)
    full_df["ebitda_total"] = pd.to_numeric(full_df["EBITDA"], errors="coerce").fillna(0.0) * pd.to_numeric(full_df["quantity"], errors="coerce").fillna(0.0)
    summary = full_df.groupby("day", as_index=False).agg(ebitda=("ebitda_total", "sum"), revenue=("revenue", "sum"))
    summary["ebitda_pct"] = summary.apply(lambda r: (float(r["ebitda"]) / float(r["revenue"]) * 100.0) if float(r["revenue"]) else 0.0, axis=1)
    return summary[["day", "ebitda", "ebitda_pct"]]


@st.cache_data(show_spinner=False, ttl=900)
def load_unit_economics_day_table(date_from: str, date_to: str, *, seller_client_id: str | None, seller_api_key: str | None, company_name: str | None) -> pd.DataFrame:
    costs_df = load_effective_unit_costs(company_name)
    raw_sales_df = _load_sales_by_sku_day_rows(date_from, date_to, seller_client_id=seller_client_id, seller_api_key=seller_api_key)
    day_sales_df = _build_day_sales(raw_sales_df)
    if costs_df.empty or day_sales_df.empty:
        return pd.DataFrame()
    rows: list[dict] = []
    for day_str in sorted(day_sales_df["day"].astype(str).unique().tolist()):
        sales_day = day_sales_df[day_sales_df["day"].astype(str) == str(day_str)].copy()
        finance_costs = _load_finance_period_costs(str(day_str), str(day_str), seller_client_id=seller_client_id, seller_api_key=seller_api_key)
        applied = _apply_unit_econ_costs(sales_day, costs_df, finance_costs)
        if applied.empty:
            continue
        qty = pd.to_numeric(applied["quantity"], errors="coerce").fillna(0.0)
        rows.append({
            "day": str(day_str),
            "revenue": float(pd.to_numeric(applied["revenue"], errors="coerce").fillna(0.0).sum()),
            "EBITDA total": float((pd.to_numeric(applied["EBITDA"], errors="coerce").fillna(0.0) * qty).sum()),
            "tea cost": float((pd.to_numeric(applied["tea_cost"], errors="coerce").fillna(0.0) * qty).sum()),
            "package cost": float((pd.to_numeric(applied["package_cost"], errors="coerce").fillna(0.0) * qty).sum()),
            "label cost": float((pd.to_numeric(applied["label_cost"], errors="coerce").fillna(0.0) * qty).sum()),
            "packing cost": float((pd.to_numeric(applied["packing_cost"], errors="coerce").fillna(0.0) * qty).sum()),
            "delivery FBO": float((pd.to_numeric(applied["delivery_fbo"], errors="coerce").fillna(0.0) * qty).sum()),
            "promotion": float((pd.to_numeric(applied["promotion"], errors="coerce").fillna(0.0) * qty).sum()),
            "ozon percent cost": float((pd.to_numeric(applied["ozon_percent_cost"], errors="coerce").fillna(0.0) * qty).sum()),
            "ozon logistics": float((pd.to_numeric(applied["ozon_logistics"], errors="coerce").fillna(0.0) * qty).sum()),
            "other costs": float((pd.to_numeric(applied["other_costs"], errors="coerce").fillna(0.0) * qty).sum()),
            "review points": float((pd.to_numeric(applied["review_points"], errors="coerce").fillna(0.0) * qty).sum()),
            "seller bonuses": float((pd.to_numeric(applied["seller_bonuses"], errors="coerce").fillna(0.0) * qty).sum()),
            "taxes": float((pd.to_numeric(applied["taxes"], errors="coerce").fillna(0.0) * qty).sum()),
            "units sold": float(qty.sum()),
        })
    return pd.DataFrame(rows)


@st.cache_data(show_spinner=False, ttl=900)
def load_unit_economics_sku_period_summary(date_from: str, date_to: str, *, seller_client_id: str | None, seller_api_key: str | None, company_name: str | None) -> pd.DataFrame:
    costs_df = load_effective_unit_costs(company_name)
    raw_sales_df = _load_sales_by_sku_day_rows(date_from, date_to, seller_client_id=seller_client_id, seller_api_key=seller_api_key)
    day_sales_df = _build_day_sales(raw_sales_df)
    if costs_df.empty or day_sales_df.empty:
        return pd.DataFrame()
    parts: list[pd.DataFrame] = []
    for day_str in sorted(day_sales_df["day"].astype(str).unique().tolist()):
        sales_day = day_sales_df[day_sales_df["day"].astype(str) == str(day_str)].copy()
        finance_costs = _load_finance_period_costs(str(day_str), str(day_str), seller_client_id=seller_client_id, seller_api_key=seller_api_key)
        applied = _apply_unit_econ_costs(sales_day, costs_df, finance_costs)
        if applied.empty:
            continue
        applied["revenue_total"] = pd.to_numeric(applied["revenue"], errors="coerce").fillna(0.0)
        applied["ebitda_total"] = pd.to_numeric(applied["EBITDA"], errors="coerce").fillna(0.0) * pd.to_numeric(applied["quantity"], errors="coerce").fillna(0.0)
        parts.append(applied)
    if not parts:
        return pd.DataFrame()
    return pd.concat(parts, ignore_index=True)


def render_unit_economics_tab(date_from: date, date_to: date, *, seller_client_id: str | None, seller_api_key: str | None, company_name: str | None) -> None:
    st.subheader("Unit Economics")
    if not seller_client_id or not seller_api_key:
        st.warning("Seller API credentials are missing for the selected company.")
        return
    if not get_unit_econ_sheet_config(company_name):
        st.info("Unit economics source is not configured for the selected company.")
        return

    col_from, col_to = st.columns(2)
    with col_from:
        period_from = st.date_input("Period from", value=date_from, key="unit_econ_from")
    with col_to:
        period_to = st.date_input("Period to", value=date_to, key="unit_econ_to")
    if period_from > period_to:
        st.error("Invalid period.")
        return

    day_table = load_unit_economics_day_table(str(period_from), str(period_to), seller_client_id=seller_client_id, seller_api_key=seller_api_key, company_name=company_name)
    if day_table.empty:
        st.info("No unit economics data for the selected period.")
        return

    with st.expander("Rules and formulas", expanded=False):
        formulas_df = pd.DataFrame([
            {"column": "tea cost", "rule": "Loaded from Unit Economics Products."},
            {"column": "package cost", "rule": "Loaded from Unit Economics Products."},
            {"column": "label cost", "rule": "Loaded from Unit Economics Products."},
            {"column": "packing cost", "rule": "Loaded from Unit Economics Products."},
            {"column": "delivery FBO", "rule": "cross_docking + acceptance for the day."},
            {"column": "promotion", "rule": "pay_per_click + promotion_with_cost_per_order for the day."},
            {"column": "ozon percent cost", "rule": "20% if sale per unit <= 300 RUB, else 31%."},
            {"column": "ozon logistics", "rule": "logistics from Finance Balance for the day."},
            {"column": "other costs", "rule": "acquiring + reverse logistics + returns + errors + storage for the day."},
            {"column": "review points", "rule": "points_for_reviews from Finance Balance for the day."},
            {"column": "seller bonuses", "rule": "seller_bonuses from Finance Balance for the day."},
            {"column": "taxes", "rule": "2.5% of sale."},
            {"column": "revenue", "rule": "Revenue from /v1/analytics/data by day."},
            {"column": "units sold", "rule": "ordered_units from /v1/analytics/data by day."},
            {"column": "EBITDA total", "rule": "Revenue minus all costs for the day."},
        ])
        st.dataframe(formulas_df, width="stretch", hide_index=True)

    revenue_total = float(pd.to_numeric(day_table["revenue"], errors="coerce").fillna(0.0).sum())
    abs_row = {"type": "absolute"}
    for col in [c for c in day_table.columns if c != "day"]:
        abs_row[col] = float(pd.to_numeric(day_table[col], errors="coerce").fillna(0.0).sum())
    pct_row = {"type": "% of revenue"}
    for col, value in abs_row.items():
        if col == "type":
            continue
        if col == "units sold":
            pct_row[col] = ""
        elif col == "revenue":
            pct_row[col] = 100.0 if revenue_total else 0.0
        else:
            pct_row[col] = (float(value) / revenue_total * 100.0) if revenue_total else 0.0
    totals_df = pd.DataFrame([abs_row, pct_row])
    totals_view = totals_df.copy()
    for col in totals_view.columns:
        if col == "type":
            continue
        abs_mask = totals_view["type"].eq("absolute")
        pct_mask = totals_view["type"].eq("% of revenue")
        totals_view.loc[abs_mask, col] = pd.to_numeric(totals_view.loc[abs_mask, col], errors="coerce").fillna(0.0).map(lambda x: f"{x:.2f}")
        totals_view.loc[pct_mask, col] = pd.to_numeric(totals_view.loc[pct_mask, col], errors="coerce").map(lambda x: "" if pd.isna(x) else f"{x:.2f}%")
    st.caption("Totals")
    st.dataframe(totals_view, width="stretch", hide_index=True)

    day_view = day_table.copy()
    day_view["day_dt"] = pd.to_datetime(day_view["day"], errors="coerce")
    day_view = day_view.sort_values("day_dt", ascending=False).drop(columns=["day_dt"], errors="ignore")
    day_view["day"] = pd.to_datetime(day_view["day"], errors="coerce").dt.strftime("%d.%m.%Y").fillna(day_view["day"].astype(str))
    numeric_cols = [col for col in day_view.columns if col != "day"]
    st.dataframe(day_view.style.format({col: "{:.0f}" for col in numeric_cols}), width="stretch", hide_index=True)
