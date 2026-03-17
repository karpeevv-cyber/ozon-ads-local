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
    load_unit_economics_sku_period_summary.clear()


@st.cache_data(show_spinner=False, ttl=1800)
def _load_unit_costs(sheet_id: str, gid: str) -> pd.DataFrame:
    resp = requests.get(_sheet_csv_url(sheet_id, gid), timeout=30)
    resp.raise_for_status()
    csv_text = resp.content.decode("utf-8-sig", errors="replace")
    raw = pd.read_csv(StringIO(csv_text), header=None, dtype=str).fillna("")

    if raw.shape[0] < 3:
        return pd.DataFrame(columns=["sku", "sheet_name", "tea_cost", "package_cost", "label_cost", "packing_cost"])

    header = [str(x).strip() for x in raw.iloc[1].tolist()]
    data = raw.iloc[2:].copy()
    data.columns = header

    if "sku" in data.columns:
        sku_series = data["sku"].astype(str).str.strip()
    else:
        sku_series = data.iloc[:, 0].astype(str).str.strip()
    data = data.copy()
    data["__sku__"] = sku_series
    data = data[data["__sku__"].str.fullmatch(r"\d+")].copy()
    if data.empty:
        return pd.DataFrame(columns=["sku", "sheet_name", "tea_cost", "package_cost", "label_cost", "packing_cost"])

    empty_series = pd.Series([""] * len(data), index=data.index, dtype=str)
    name_part_1 = data.iloc[:, 1].astype(str).str.strip() if data.shape[1] > 1 else empty_series
    name_part_2 = data.iloc[:, 2].astype(str).str.strip() if data.shape[1] > 2 else empty_series
    sheet_name = (name_part_1.fillna("") + " " + name_part_2.fillna("")).str.strip()

    tea_cost_col = data["себес порции чая"] if "себес порции чая" in data.columns else empty_series
    package_cost_col = data["косты уп"] if "косты уп" in data.columns else empty_series
    label_cost_col = data["этикетки"] if "этикетки" in data.columns else empty_series
    packing_cost_col = data["фасовка"] if "фасовка" in data.columns else empty_series

    return pd.DataFrame(
        {
            "sku": data["__sku__"].astype(str),
            "sheet_name": sheet_name,
            "tea_cost": tea_cost_col.apply(_to_num),
            "package_cost": package_cost_col.apply(_to_num),
            "label_cost": label_cost_col.apply(_to_num),
            "packing_cost": packing_cost_col.apply(_to_num),
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
def _load_sales_by_sku_day_rows(
    date_from: str,
    date_to: str,
    *,
    seller_client_id: str | None,
    seller_api_key: str | None,
) -> pd.DataFrame:
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
            sku = str((dims[0] or {}).get("id", "")).strip() if len(dims) > 0 else ""
            name = str((dims[0] or {}).get("name", "")).strip() if len(dims) > 0 else ""
            day = str((dims[1] or {}).get("id", "")).strip() if len(dims) > 1 else ""
            revenue = _to_num(metrics[0] if len(metrics) > 0 else 0)
            ordered_units = int(round(_to_num(metrics[1] if len(metrics) > 1 else 0)))
            if not sku:
                continue
            rows.append({"sku": sku, "name": name, "day": day, "revenue": revenue, "ordered_units": ordered_units})

        if len(data) < limit:
            break
        offset += limit

    if not rows:
        return pd.DataFrame(columns=["sku", "name", "day", "revenue", "ordered_units"])
    return pd.DataFrame(rows)


@st.cache_data(show_spinner=False, ttl=900)
def _load_sales_by_sku(
    date_from: str,
    date_to: str,
    *,
    seller_client_id: str | None,
    seller_api_key: str | None,
) -> pd.DataFrame:
    df = _load_sales_by_sku_day_rows(
        date_from,
        date_to,
        seller_client_id=seller_client_id,
        seller_api_key=seller_api_key,
    )
    if df.empty:
        return pd.DataFrame(columns=["sku", "name", "quantity", "revenue", "sale"])

    grouped = (
        df.groupby("sku", as_index=False)
        .agg(quantity=("ordered_units", "sum"), revenue=("revenue", "sum"), name=("name", "first"))
    )
    grouped = grouped[grouped["quantity"] > 0].copy()
    grouped["sale"] = grouped.apply(
        lambda r: (float(r["revenue"]) / float(r["quantity"])) if float(r["quantity"]) > 0 else 0.0,
        axis=1,
    )
    return grouped


@st.cache_data(show_spinner=False, ttl=900)
def _load_finance_period_costs(
    date_from: str,
    date_to: str,
    *,
    seller_client_id: str | None,
    seller_api_key: str | None,
) -> dict[str, float]:
    payload = seller_finance_balance(
        date_from=date_from,
        date_to=date_to,
        client_id=seller_client_id,
        api_key=seller_api_key,
    )
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
    merged["позиция"] = merged["name"].astype(str).str.strip()
    missing_name = merged["позиция"].eq("")
    merged.loc[missing_name, "позиция"] = merged.loc[missing_name, "sheet_name"].astype(str).str.strip()

    for col in ["tea_cost", "package_cost", "label_cost", "packing_cost"]:
        merged[col] = pd.to_numeric(merged[col], errors="coerce").fillna(0.0)

    merged["Доставка на ФБО"] = (finance_costs["cross_docking"] + finance_costs["acceptance"]) / total_units
    merged["продвижение"] = (finance_costs["marketing"] + finance_costs["promotion_with_cpo"]) / total_units
    merged["Косты Озон %"] = merged["sale"].apply(lambda x: float(x) * (0.20 if float(x) <= 300 else 0.31))
    merged["Ozon касты логистика"] = finance_costs["logistics"] / total_units
    merged["касты другое"] = (
        finance_costs["acquiring"]
        + finance_costs["reverse_logistics"]
        + finance_costs["returns_processing"]
        + finance_costs["errors"]
        + finance_costs["storage"]
    ) / total_units
    merged["баллы за отзывы"] = finance_costs["points_for_reviews"] / total_units
    merged["бонусы продавца"] = finance_costs["seller_bonuses"] / total_units
    merged["налоги"] = merged["sale"].astype(float) * 0.025
    merged["EBITDA"] = (
        merged["sale"].astype(float)
        - merged["tea_cost"]
        - merged["package_cost"]
        - merged["label_cost"]
        - merged["packing_cost"]
        - merged["Доставка на ФБО"]
        - merged["продвижение"]
        - merged["Косты Озон %"]
        - merged["Ozon касты логистика"]
        - merged["касты другое"]
        - merged["баллы за отзывы"]
        - merged["бонусы продавца"]
        - merged["налоги"]
    )
    merged["ebitda_pct"] = merged.apply(
        lambda r: (float(r["EBITDA"]) / float(r["sale"]) * 100.0) if float(r["sale"]) else 0.0,
        axis=1,
    )
    return merged


@st.cache_data(show_spinner=False, ttl=900)
def load_unit_economics_daily_summary(
    date_from: str,
    date_to: str,
    *,
    seller_client_id: str | None,
    seller_api_key: str | None,
    company_name: str | None,
) -> pd.DataFrame:
    costs_df = load_effective_unit_costs(company_name)
    if costs_df.empty:
        return pd.DataFrame(columns=["day", "ebitda", "ebitda_pct"])

    raw_sales_df = _load_sales_by_sku_day_rows(
        date_from,
        date_to,
        seller_client_id=seller_client_id,
        seller_api_key=seller_api_key,
    )
    if raw_sales_df.empty:
        return pd.DataFrame(columns=["day", "ebitda", "ebitda_pct"])

    day_sales_df = (
        raw_sales_df.groupby(["day", "sku"], as_index=False)
        .agg(quantity=("ordered_units", "sum"), revenue=("revenue", "sum"), name=("name", "first"))
    )
    day_sales_df = day_sales_df[day_sales_df["quantity"] > 0].copy()
    if day_sales_df.empty:
        return pd.DataFrame(columns=["day", "ebitda", "ebitda_pct"])

    day_sales_df["sale"] = day_sales_df.apply(
        lambda r: (float(r["revenue"]) / float(r["quantity"])) if float(r["quantity"]) > 0 else 0.0,
        axis=1,
    )

    parts: list[pd.DataFrame] = []
    for day_str in sorted(day_sales_df["day"].astype(str).unique().tolist()):
        sales_day = day_sales_df[day_sales_df["day"].astype(str) == str(day_str)].copy()
        finance_costs = _load_finance_period_costs(
            str(day_str),
            str(day_str),
            seller_client_id=seller_client_id,
            seller_api_key=seller_api_key,
        )
        applied = _apply_unit_econ_costs(sales_day, costs_df, finance_costs)
        if applied.empty:
            continue
        applied["day"] = str(day_str)
        parts.append(applied)

    if not parts:
        return pd.DataFrame(columns=["day", "ebitda", "ebitda_pct"])

    full_df = pd.concat(parts, ignore_index=True)
    full_df["ebitda_total"] = (
        pd.to_numeric(full_df["EBITDA"], errors="coerce").fillna(0.0)
        * pd.to_numeric(full_df["quantity"], errors="coerce").fillna(0.0)
    )
    summary = full_df.groupby("day", as_index=False).agg(ebitda=("ebitda_total", "sum"), revenue=("revenue", "sum"))
    summary["ebitda_pct"] = summary.apply(
        lambda r: (float(r["ebitda"]) / float(r["revenue"]) * 100.0) if float(r["revenue"]) else 0.0,
        axis=1,
    )
    return summary[["day", "ebitda", "ebitda_pct"]]


@st.cache_data(show_spinner=False, ttl=900)
def load_unit_economics_day_table(
    date_from: str,
    date_to: str,
    *,
    seller_client_id: str | None,
    seller_api_key: str | None,
    company_name: str | None,
) -> pd.DataFrame:
    costs_df = load_effective_unit_costs(company_name)
    if costs_df.empty:
        return pd.DataFrame()

    raw_sales_df = _load_sales_by_sku_day_rows(
        date_from,
        date_to,
        seller_client_id=seller_client_id,
        seller_api_key=seller_api_key,
    )
    if raw_sales_df.empty:
        return pd.DataFrame()

    day_sales_df = (
        raw_sales_df.groupby(["day", "sku"], as_index=False)
        .agg(quantity=("ordered_units", "sum"), revenue=("revenue", "sum"), name=("name", "first"))
    )
    day_sales_df = day_sales_df[day_sales_df["quantity"] > 0].copy()
    if day_sales_df.empty:
        return pd.DataFrame()

    day_sales_df["sale"] = day_sales_df.apply(
        lambda r: (float(r["revenue"]) / float(r["quantity"])) if float(r["quantity"]) > 0 else 0.0,
        axis=1,
    )

    rows: list[dict] = []
    for day_str in sorted(day_sales_df["day"].astype(str).unique().tolist()):
        sales_day = day_sales_df[day_sales_df["day"].astype(str) == str(day_str)].copy()
        finance_costs = _load_finance_period_costs(
            str(day_str),
            str(day_str),
            seller_client_id=seller_client_id,
            seller_api_key=seller_api_key,
        )
        applied = _apply_unit_econ_costs(sales_day, costs_df, finance_costs)
        if applied.empty:
            continue

        qty = pd.to_numeric(applied["quantity"], errors="coerce").fillna(0.0)
        row = {
            "день": str(day_str),
            "себестоимость порции чая": float((pd.to_numeric(applied["tea_cost"], errors="coerce").fillna(0.0) * qty).sum()),
            "косты упаковки": float((pd.to_numeric(applied["package_cost"], errors="coerce").fillna(0.0) * qty).sum()),
            "косты этикетки": float((pd.to_numeric(applied["label_cost"], errors="coerce").fillna(0.0) * qty).sum()),
            "косты фасовки": float((pd.to_numeric(applied["packing_cost"], errors="coerce").fillna(0.0) * qty).sum()),
            "Доставка на ФБО": float((pd.to_numeric(applied["Доставка на ФБО"], errors="coerce").fillna(0.0) * qty).sum()),
            "продвижение": float((pd.to_numeric(applied["продвижение"], errors="coerce").fillna(0.0) * qty).sum()),
            "Косты Озон %": float((pd.to_numeric(applied["Косты Озон %"], errors="coerce").fillna(0.0) * qty).sum()),
            "Ozon касты логистика": float((pd.to_numeric(applied["Ozon касты логистика"], errors="coerce").fillna(0.0) * qty).sum()),
            "касты другое": float((pd.to_numeric(applied["касты другое"], errors="coerce").fillna(0.0) * qty).sum()),
            "баллы за отзывы": float((pd.to_numeric(applied["баллы за отзывы"], errors="coerce").fillna(0.0) * qty).sum()),
            "бонусы продавца": float((pd.to_numeric(applied["бонусы продавца"], errors="coerce").fillna(0.0) * qty).sum()),
            "налоги": float((pd.to_numeric(applied["налоги"], errors="coerce").fillna(0.0) * qty).sum()),
            "количество проданных позиций": float(qty.sum()),
            "выручка": float(pd.to_numeric(applied["revenue"], errors="coerce").fillna(0.0).sum()),
            "EBITDA total": float((pd.to_numeric(applied["EBITDA"], errors="coerce").fillna(0.0) * qty).sum()),
        }
        rows.append(row)

    return pd.DataFrame(rows)


@st.cache_data(show_spinner=False, ttl=900)
def load_unit_economics_sku_period_summary(
    date_from: str,
    date_to: str,
    *,
    seller_client_id: str | None,
    seller_api_key: str | None,
    company_name: str | None,
) -> pd.DataFrame:
    costs_df = load_effective_unit_costs(company_name)
    if costs_df.empty:
        return pd.DataFrame()

    raw_sales_df = _load_sales_by_sku_day_rows(
        date_from,
        date_to,
        seller_client_id=seller_client_id,
        seller_api_key=seller_api_key,
    )
    if raw_sales_df.empty:
        return pd.DataFrame()

    day_sales_df = (
        raw_sales_df.groupby(["day", "sku"], as_index=False)
        .agg(quantity=("ordered_units", "sum"), revenue=("revenue", "sum"), name=("name", "first"))
    )
    day_sales_df = day_sales_df[day_sales_df["quantity"] > 0].copy()
    if day_sales_df.empty:
        return pd.DataFrame()

    day_sales_df["sale"] = day_sales_df.apply(
        lambda r: (float(r["revenue"]) / float(r["quantity"])) if float(r["quantity"]) > 0 else 0.0,
        axis=1,
    )

    parts: list[pd.DataFrame] = []
    for day_str in sorted(day_sales_df["day"].astype(str).unique().tolist()):
        sales_day = day_sales_df[day_sales_df["day"].astype(str) == str(day_str)].copy()
        finance_costs = _load_finance_period_costs(
            str(day_str),
            str(day_str),
            seller_client_id=seller_client_id,
            seller_api_key=seller_api_key,
        )
        applied = _apply_unit_econ_costs(sales_day, costs_df, finance_costs)
        if applied.empty:
            continue
        applied["revenue_total"] = pd.to_numeric(applied["revenue"], errors="coerce").fillna(0.0)
        applied["ebitda_total"] = (
            pd.to_numeric(applied["EBITDA"], errors="coerce").fillna(0.0)
            * pd.to_numeric(applied["quantity"], errors="coerce").fillna(0.0)
        )
        for col in [
            "tea_cost",
            "package_cost",
            "label_cost",
            "packing_cost",
            "Доставка на ФБО",
            "продвижение",
            "Косты Озон %",
            "Ozon касты логистика",
            "касты другое",
            "баллы за отзывы",
            "бонусы продавца",
            "налоги",
            "sale",
        ]:
            applied[f"{col}__total"] = (
                pd.to_numeric(applied[col], errors="coerce").fillna(0.0)
                * pd.to_numeric(applied["quantity"], errors="coerce").fillna(0.0)
            )
        parts.append(applied)

    if not parts:
        return pd.DataFrame()

    full_df = pd.concat(parts, ignore_index=True)
    grouped = (
        full_df.groupby("sku", as_index=False)
        .agg(
            позиция=("позиция", "first"),
            quantity=("quantity", "sum"),
            revenue=("revenue_total", "sum"),
            tea_cost_total=("tea_cost__total", "sum"),
            package_cost_total=("package_cost__total", "sum"),
            label_cost_total=("label_cost__total", "sum"),
            packing_cost_total=("packing_cost__total", "sum"),
            delivery_fbo_total=("Доставка на ФБО__total", "sum"),
            promotion_total=("продвижение__total", "sum"),
            ozon_cost_pct_total=("Косты Озон %__total", "sum"),
            ozon_logistics_total=("Ozon касты логистика__total", "sum"),
            other_total=("касты другое__total", "sum"),
            reviews_total=("баллы за отзывы__total", "sum"),
            seller_bonuses_total=("бонусы продавца__total", "sum"),
            taxes_total=("налоги__total", "sum"),
            sale_total=("sale__total", "sum"),
            ebitda_total=("ebitda_total", "sum"),
        )
    )

    qty = pd.to_numeric(grouped["quantity"], errors="coerce").replace(0, pd.NA)
    grouped["sale"] = (pd.to_numeric(grouped["sale_total"], errors="coerce") / qty).fillna(0.0)
    grouped["tea_cost"] = (pd.to_numeric(grouped["tea_cost_total"], errors="coerce") / qty).fillna(0.0)
    grouped["package_cost"] = (pd.to_numeric(grouped["package_cost_total"], errors="coerce") / qty).fillna(0.0)
    grouped["label_cost"] = (pd.to_numeric(grouped["label_cost_total"], errors="coerce") / qty).fillna(0.0)
    grouped["packing_cost"] = (pd.to_numeric(grouped["packing_cost_total"], errors="coerce") / qty).fillna(0.0)
    grouped["Доставка на ФБО"] = (pd.to_numeric(grouped["delivery_fbo_total"], errors="coerce") / qty).fillna(0.0)
    grouped["продвижение"] = (pd.to_numeric(grouped["promotion_total"], errors="coerce") / qty).fillna(0.0)
    grouped["Косты Озон %"] = (pd.to_numeric(grouped["ozon_cost_pct_total"], errors="coerce") / qty).fillna(0.0)
    grouped["Ozon касты логистика"] = (pd.to_numeric(grouped["ozon_logistics_total"], errors="coerce") / qty).fillna(0.0)
    grouped["касты другое"] = (pd.to_numeric(grouped["other_total"], errors="coerce") / qty).fillna(0.0)
    grouped["баллы за отзывы"] = (pd.to_numeric(grouped["reviews_total"], errors="coerce") / qty).fillna(0.0)
    grouped["бонусы продавца"] = (pd.to_numeric(grouped["seller_bonuses_total"], errors="coerce") / qty).fillna(0.0)
    grouped["налоги"] = (pd.to_numeric(grouped["taxes_total"], errors="coerce") / qty).fillna(0.0)
    grouped["EBITDA"] = (pd.to_numeric(grouped["ebitda_total"], errors="coerce") / qty).fillna(0.0)
    grouped["ebitda_pct"] = grouped.apply(
        lambda r: (float(r["ebitda_total"]) / float(r["revenue"]) * 100.0) if float(r["revenue"]) else 0.0,
        axis=1,
    )
    return grouped


def render_unit_economics_tab(
    date_from: date,
    date_to: date,
    *,
    seller_client_id: str | None,
    seller_api_key: str | None,
    company_name: str | None,
) -> None:
    st.subheader("Юнит экономика")

    if not seller_client_id or not seller_api_key:
        st.warning("Seller creds are missing for selected company.")
        return

    if not get_unit_econ_sheet_config(company_name):
        st.info("None")
        return

    col_from, col_to = st.columns(2)
    with col_from:
        period_from = st.date_input("Период с", value=date_from, key="unit_econ_from")
    with col_to:
        period_to = st.date_input("Период по", value=date_to, key="unit_econ_to")

    if period_from > period_to:
        st.error("Период указан некорректно.")
        return

    day_table = load_unit_economics_day_table(
        str(period_from),
        str(period_to),
        seller_client_id=seller_client_id,
        seller_api_key=seller_api_key,
        company_name=company_name,
    )
    if day_table.empty:
        st.info("None")
        return

    with st.expander("Правила и формулы расчёта", expanded=False):
        formulas_df = pd.DataFrame(
            [
                {"столбец": "SKU", "правило": "Ozon SKU товара, ключ связки с продажами и костами."},
                {"столбец": "позиция", "правило": "Название позиции. Приоритет: название из продаж Ozon, затем название из таблицы товаров/Google Sheet."},
                {"столбец": "себестоимость порции чая", "правило": "Берётся из основы юнит-экономики для выбранного магазина."},
                {"столбец": "косты упаковки", "правило": "Берётся из основы юнит-экономики для выбранного магазина."},
                {"столбец": "косты этикетки", "правило": "Берётся из основы юнит-экономики для выбранного магазина."},
                {"столбец": "косты фасовки", "правило": "Берётся из основы юнит-экономики для выбранного магазина."},
                {"столбец": "Доставка на ФБО", "правило": "(cross_docking + goods_processing_in_shipment) за день / количество проданных штук за этот день."},
                {"столбец": "продвижение", "правило": "(pay_per_click + promotion_with_cost_per_order) за день / количество проданных штук за этот день."},
                {"столбец": "Косты Озон %", "правило": "Если продажа за 1 шт <= 300 ₽, то 20% от продажи; если > 300 ₽, то 31% от продажи."},
                {"столбец": "Ozon касты логистика", "правило": "logistics за день / количество проданных штук за этот день."},
                {"столбец": "касты другое", "правило": "(acquiring + reverse_logistics + partner_returns_cancellations_processing + booking_space_and_staff_for_partial_shipment + product_placement_in_ozon_warehouses) за день / количество проданных штук за этот день."},
                {"столбец": "баллы за отзывы", "правило": "points_for_reviews за день / количество проданных штук за этот день."},
                {"столбец": "бонусы продавца", "правило": "seller_bonuses за день / количество проданных штук за этот день."},
                {"столбец": "налоги", "правило": "2.5% от продажи за 1 штуку."},
                {"столбец": "продажа", "правило": "Выручка по SKU / количество проданных штук за период."},
                {"столбец": "количество проданных позиций", "правило": "Сумма ordered_units по SKU за выбранный период."},
                {"столбец": "выручка", "правило": "Сумма revenue по SKU за выбранный период из /v1/analytics/data."},
                {"столбец": "EBITDA", "правило": "Продажа - все косты на 1 штуку."},
                {"столбец": "EBITDA total", "правило": "EBITDA на 1 штуку * количество проданных позиций."},
                {"столбец": "Итого: абсолют", "правило": "Сумма абсолютных значений по всем SKU за выбранный период."},
                {"столбец": "Итого: % от выручки", "правило": "Абсолютное значение статьи / общая выручка периода * 100%."},
            ]
        )
        st.dataframe(formulas_df, width="stretch", hide_index=True)

    revenue_total = float(pd.to_numeric(day_table["выручка"], errors="coerce").fillna(0.0).sum())
    totals_abs = {
        "тип": "абсолют",
        "себестоимость порции чая": float(pd.to_numeric(day_table["себестоимость порции чая"], errors="coerce").fillna(0.0).sum()),
        "косты упаковки": float(pd.to_numeric(day_table["косты упаковки"], errors="coerce").fillna(0.0).sum()),
        "косты этикетки": float(pd.to_numeric(day_table["косты этикетки"], errors="coerce").fillna(0.0).sum()),
        "косты фасовки": float(pd.to_numeric(day_table["косты фасовки"], errors="coerce").fillna(0.0).sum()),
        "Доставка на ФБО": float(pd.to_numeric(day_table["Доставка на ФБО"], errors="coerce").fillna(0.0).sum()),
        "продвижение": float(pd.to_numeric(day_table["продвижение"], errors="coerce").fillna(0.0).sum()),
        "Косты Озон %": float(pd.to_numeric(day_table["Косты Озон %"], errors="coerce").fillna(0.0).sum()),
        "Ozon касты логистика": float(pd.to_numeric(day_table["Ozon касты логистика"], errors="coerce").fillna(0.0).sum()),
        "касты другое": float(pd.to_numeric(day_table["касты другое"], errors="coerce").fillna(0.0).sum()),
        "баллы за отзывы": float(pd.to_numeric(day_table["баллы за отзывы"], errors="coerce").fillna(0.0).sum()),
        "бонусы продавца": float(pd.to_numeric(day_table["бонусы продавца"], errors="coerce").fillna(0.0).sum()),
        "налоги": float(pd.to_numeric(day_table["налоги"], errors="coerce").fillna(0.0).sum()),
        "количество проданных позиций": float(pd.to_numeric(day_table["количество проданных позиций"], errors="coerce").fillna(0.0).sum()),
        "выручка": revenue_total,
        "EBITDA total": float(pd.to_numeric(day_table["EBITDA total"], errors="coerce").fillna(0.0).sum()),
    }
    totals_pct = {"тип": "% от выручки"}
    for col, val in totals_abs.items():
        if col == "тип":
            continue
        if col == "количество проданных позиций":
            totals_pct[col] = ""
        elif col == "выручка":
            totals_pct[col] = 100.0 if revenue_total else 0.0
        else:
            totals_pct[col] = (float(val) / revenue_total * 100.0) if revenue_total else 0.0
    totals_df = pd.DataFrame([totals_abs, totals_pct])

    numeric_cols = [
        "выручка",
        "EBITDA total",
        "себестоимость порции чая",
        "косты упаковки",
        "косты этикетки",
        "косты фасовки",
        "Доставка на ФБО",
        "продвижение",
        "Косты Озон %",
        "Ozon касты логистика",
        "касты другое",
        "баллы за отзывы",
        "бонусы продавца",
        "налоги",
        "количество проданных позиций",
    ]

    st.caption("Итого за выбранный период")
    totals_view = totals_df.copy()
    for col in totals_view.columns:
        if col == "тип":
            continue
        abs_mask = totals_view["тип"].eq("абсолют")
        pct_mask = totals_view["тип"].eq("% от выручки")
        totals_view.loc[abs_mask, col] = pd.to_numeric(totals_view.loc[abs_mask, col], errors="coerce").fillna(0.0).map(lambda x: f"{x:.2f}")
        totals_view.loc[pct_mask, col] = pd.to_numeric(totals_view.loc[pct_mask, col], errors="coerce").map(
            lambda x: "" if pd.isna(x) else f"{x:.2f}%"
        )
    st.dataframe(totals_view, width="stretch", hide_index=True)
    day_view = day_table.copy()
    day_cols = [
        "день",
        "выручка",
        "EBITDA total",
        "себестоимость порции чая",
        "косты упаковки",
        "косты этикетки",
        "косты фасовки",
        "Доставка на ФБО",
        "продвижение",
        "Косты Озон %",
        "Ozon касты логистика",
        "касты другое",
        "баллы за отзывы",
        "бонусы продавца",
        "налоги",
        "количество проданных позиций",
    ]
    day_view = day_view[[c for c in day_cols if c in day_view.columns]]
    if "день" in day_view.columns:
        day_view["день_dt"] = pd.to_datetime(day_view["день"], errors="coerce")
        day_view = day_view.sort_values("день_dt", ascending=False).drop(columns=["день_dt"], errors="ignore")
        day_view["день"] = pd.to_datetime(day_view["день"], errors="coerce").dt.strftime("%d.%m.%Y").fillna(day_view["день"].astype(str))
    st.dataframe(day_view.style.format({col: "{:.0f}" for col in numeric_cols}), width="stretch", hide_index=True)
