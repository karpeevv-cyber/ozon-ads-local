# -*- coding: utf-8 -*-
from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st

from clients_seller import seller_product_info_list, seller_product_list
from ui_unit_economics_tab import (
    _load_sales_by_sku,
    _load_unit_cost_overrides,
    get_unit_econ_products_path,
    get_unit_econ_sheet_config,
    load_effective_unit_costs,
    save_unit_cost_overrides,
)


@st.cache_data(show_spinner=False, ttl=900)
def _load_all_product_ids(*, seller_client_id: str, seller_api_key: str) -> list[str]:
    out: list[str] = []
    last_id = ""
    seen_last_ids: set[str] = set()
    while True:
        resp = seller_product_list(last_id=last_id, limit=1000, visibility="ALL", client_id=seller_client_id, api_key=seller_api_key)
        result = resp.get("result", {}) or {}
        items = result.get("items", []) or []
        if not items:
            break
        for it in items:
            pid = it.get("product_id")
            if pid is not None:
                out.append(str(pid))
        next_last_id = str(result.get("last_id", "")) if result.get("last_id") is not None else ""
        if not next_last_id or next_last_id in seen_last_ids:
            break
        seen_last_ids.add(next_last_id)
        last_id = next_last_id
    return list(dict.fromkeys(out))


@st.cache_data(show_spinner=False, ttl=900)
def _load_sku_title_map(*, seller_client_id: str, seller_api_key: str) -> dict[str, str]:
    product_ids = _load_all_product_ids(seller_client_id=seller_client_id, seller_api_key=seller_api_key)
    if not product_ids:
        return {}
    out: dict[str, str] = {}
    for i in range(0, len(product_ids), 1000):
        batch = product_ids[i : i + 1000]
        resp = seller_product_info_list(product_ids=batch, client_id=seller_client_id, api_key=seller_api_key)
        for it in resp.get("items", []) or []:
            sku = it.get("sku")
            if sku is not None:
                out[str(sku)] = str(it.get("name") or it.get("offer_id") or "").strip()
    return out


def render_unit_economics_products_tab(
    date_from: date,
    date_to: date,
    *,
    seller_client_id: str | None,
    seller_api_key: str | None,
    company_name: str | None,
) -> None:
    st.subheader("Unit Economics Products")
    if not seller_client_id or not seller_api_key:
        st.warning("Seller API credentials are missing for the selected company.")
        return
    if not get_unit_econ_sheet_config(company_name):
        st.info("Unit economics source is not configured for the selected company.")
        return

    costs_df = load_effective_unit_costs(company_name).rename(columns={"sheet_name": "sheet_title"})
    if costs_df.empty:
        st.info("No products found in the unit economics source.")
        return

    sales_df = _load_sales_by_sku(str(date_from), str(date_to), seller_client_id=seller_client_id, seller_api_key=seller_api_key)
    sku_title_map = _load_sku_title_map(seller_client_id=seller_client_id, seller_api_key=seller_api_key)
    overrides_df = _load_unit_cost_overrides(get_unit_econ_products_path(company_name))

    sales_name_df = pd.DataFrame(columns=["sku", "sales_name"])
    if not sales_df.empty and "name" in sales_df.columns:
        sales_name_df = sales_df[["sku", "name"]].rename(columns={"name": "sales_name"})

    view_df = costs_df.merge(sales_name_df, on="sku", how="left")
    if not overrides_df.empty:
        view_df = view_df.merge(overrides_df[["sku", "position"]].rename(columns={"position": "saved_name"}), on="sku", how="left")
    else:
        view_df["saved_name"] = ""

    view_df["ozon_name"] = view_df["sku"].astype(str).map(sku_title_map).fillna("").astype(str).str.strip()
    view_df["sales_name"] = view_df["sales_name"].fillna("").astype(str).str.strip()
    view_df["saved_name"] = view_df["saved_name"].fillna("").astype(str).str.strip()
    view_df["sheet_title"] = view_df["sheet_title"].fillna("").astype(str).str.strip()
    view_df["name"] = view_df["ozon_name"]
    for source_col in ["sales_name", "saved_name", "sheet_title"]:
        missing = view_df["name"].eq("")
        view_df.loc[missing, "name"] = view_df.loc[missing, source_col]

    for col in ["tea_cost", "package_cost", "label_cost", "packing_cost"]:
        view_df[col] = pd.to_numeric(view_df[col], errors="coerce").fillna(0.0)

    editor_df = (
        view_df[["sku", "name", "tea_cost", "package_cost", "label_cost", "packing_cost"]]
        .rename(
            columns={
                "sku": "SKU",
                "name": "name",
                "tea_cost": "tea cost",
                "package_cost": "package cost",
                "label_cost": "label cost",
                "packing_cost": "packing cost",
            }
        )
        .sort_values(["SKU"], ascending=[True])
        .reset_index(drop=True)
    )

    edited_df = st.data_editor(
        editor_df,
        width="stretch",
        hide_index=True,
        disabled=["SKU"],
        column_config={
            "SKU": st.column_config.TextColumn("SKU"),
            "name": st.column_config.TextColumn("name"),
            "tea cost": st.column_config.NumberColumn("tea cost", format="%.2f"),
            "package cost": st.column_config.NumberColumn("package cost", format="%.2f"),
            "label cost": st.column_config.NumberColumn("label cost", format="%.2f"),
            "packing cost": st.column_config.NumberColumn("packing cost", format="%.2f"),
        },
        key="unit_econ_products_editor",
    )

    if st.button("Save Unit Economics Products", key="save_unit_econ_products"):
        save_df = edited_df.rename(
            columns={
                "SKU": "sku",
                "name": "position",
                "tea cost": "tea_cost",
                "package cost": "package_cost",
                "label cost": "label_cost",
                "packing cost": "packing_cost",
            }
        )[["sku", "position", "tea_cost", "package_cost", "label_cost", "packing_cost"]].copy()

        existing = overrides_df.copy()
        if existing.empty:
            merged = save_df
        else:
            existing = existing[~existing["sku"].isin(save_df["sku"].astype(str))].copy()
            merged = pd.concat([existing, save_df], ignore_index=True)
        save_unit_cost_overrides(merged, get_unit_econ_products_path(company_name))
        st.success("Unit economics products saved.")
