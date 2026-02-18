# -*- coding: utf-8 -*-
from __future__ import annotations

from datetime import date, timedelta
import math

import pandas as pd
import streamlit as st

from clients_seller import seller_finance_balance


def _daterange(d_from: date, d_to: date):
    d = d_from
    while d <= d_to:
        yield d
        d += timedelta(days=1)


def _ceil_int(value) -> int:
    try:
        return int(math.ceil(float(value)))
    except Exception:
        return 0


def _fetch_balance_day(
    day_str: str,
    *,
    seller_client_id: str | None,
    seller_api_key: str | None,
):
    return seller_finance_balance(
        date_from=day_str,
        date_to=day_str,
        client_id=seller_client_id,
        api_key=seller_api_key,
    )


@st.cache_data(show_spinner=False)
def _fetch_finance_rows_cached_static(
    date_from: date,
    date_to: date,
    *,
    seller_client_id: str | None,
    seller_api_key: str | None,
):
    rows = []
    days = list(_daterange(date_from, date_to))
    for d in reversed(days):
        day_str = d.isoformat()
        data = _fetch_balance_day(
            day_str,
            seller_client_id=seller_client_id,
            seller_api_key=seller_api_key,
        )
        total = data.get("total", {}) or {}
        cashflows = data.get("cashflows", {}) or {}

        opening_balance = total.get("opening_balance", {}).get("value", 0)
        closing_balance = total.get("closing_balance", {}).get("value", 0)
        accrued = total.get("accrued", {}).get("value", 0)
        payments_list = total.get("payments", []) or []
        payments = sum(float(p.get("value", 0) or 0) for p in payments_list)

        sales = cashflows.get("sales", {}).get("amount", {}).get("value", 0)
        fee = cashflows.get("sales", {}).get("fee", {}).get("value", 0)

        services = cashflows.get("services", []) or []
        logistics = 0.0
        cross_docking = 0.0
        storage = 0.0
        marketing = 0.0
        promotion_with_cpo = 0.0
        acquiring = 0.0
        seller_bonuses = 0.0
        points_for_reviews = 0.0
        for s in services:
            name = str(s.get("name", "") or "")
            val = float(s.get("amount", {}).get("value", 0) or 0)
            if name in {"logistics", "courier_client_reinvoice"}:
                logistics += val
            if name == "cross_docking":
                cross_docking += val
            if name == "product_placement_in_ozon_warehouses":
                storage += val
            if name == "pay_per_click":
                marketing += val
            if name == "promotion_with_cost_per_order":
                promotion_with_cpo += val
            if name == "acquiring":
                acquiring += val
            if name == "seller_bonuses":
                seller_bonuses += val
            if name == "points_for_reviews":
                points_for_reviews += val

        sales_val = float(sales or 0)
        pct_logistics = (logistics / sales_val * 100.0) if sales_val else 0.0
        check_value = (
            sales
            + fee
            + acquiring
            + logistics
            + cross_docking
            + storage
            + marketing
            + promotion_with_cpo
            + points_for_reviews
            + seller_bonuses
            - accrued
        )

        rows.append(
            {
                "день": d.strftime("%d.%m.%Y"),
                "на начало дня": _ceil_int(opening_balance),
                "на конец дня": _ceil_int(closing_balance),
                "изменение": _ceil_int(accrued),
                "продажи": _ceil_int(sales),
                "комиссия": _ceil_int(fee),
                "эквайринг": _ceil_int(acquiring),
                "выплаты": _ceil_int(payments),
                "логистика": _ceil_int(logistics),
                "кросс-докинг": _ceil_int(cross_docking),
                "Хранение": _ceil_int(storage),
                "реклама": _ceil_int(marketing),
                "реклама - за заказ": _ceil_int(promotion_with_cpo),
                "баллы за отзывы": _ceil_int(points_for_reviews),
                "бонусы продавца": _ceil_int(seller_bonuses),
                "проверка": _ceil_int(check_value),
                "% логистики": round(pct_logistics, 1),
            }
        )
    return rows


@st.cache_data(show_spinner=False, ttl=1800)
def _fetch_finance_rows_cached_today(
    date_from: date,
    date_to: date,
    *,
    seller_client_id: str | None,
    seller_api_key: str | None,
):
    return _fetch_finance_rows_cached_static(
        date_from,
        date_to,
        seller_client_id=seller_client_id,
        seller_api_key=seller_api_key,
    )


def render_finance_tab(
    date_from: date,
    date_to: date,
    *,
    seller_client_id: str | None,
    seller_api_key: str | None,
    refresh_finance: bool = False,
) -> None:
    st.subheader("Баланс по дням")

    if not seller_client_id or not seller_api_key:
        st.warning("Seller creds are missing for selected company.")
        return

    if refresh_finance:
        _fetch_finance_rows_cached_static.clear()
        _fetch_finance_rows_cached_today.clear()

    today = date.today()
    if date_from <= today <= date_to:
        rows = _fetch_finance_rows_cached_today(
            date_from,
            date_to,
            seller_client_id=seller_client_id,
            seller_api_key=seller_api_key,
        )
    else:
        rows = _fetch_finance_rows_cached_static(
            date_from,
            date_to,
            seller_client_id=seller_client_id,
            seller_api_key=seller_api_key,
        )

    if not rows:
        st.info("No data for selected period.")
        return

    df = pd.DataFrame(rows)
    cols = [
        "день",
        "на начало дня",
        "на конец дня",
        "изменение",
        "продажи",
        "комиссия",
        "эквайринг",
        "выплаты",
        "логистика",
        "кросс-докинг",
        "Хранение",
        "реклама",
        "реклама - за заказ",
        "баллы за отзывы",
        "бонусы продавца",
        "проверка",
        "% логистики",
    ]
    df = df[[c for c in cols if c in df.columns]]
    if "% логистики" in df.columns:
        df["% логистики"] = pd.to_numeric(df["% логистики"], errors="coerce").round(1)

    highlight_cols = {"на начало дня", "на конец дня", "продажи", "изменение"}

    def _highlight(row):
        return ["background-color: #FFF3BF" if col in highlight_cols else "" for col in row.index]

    style = df.style.apply(_highlight, axis=1)
    if "% логистики" in df.columns:
        style = style.format({"% логистики": "{:.1f}%"})
    st.dataframe(style, width="stretch", hide_index=True)
