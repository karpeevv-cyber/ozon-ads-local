# -*- coding: utf-8 -*-
import streamlit as st
import pandas as pd
from datetime import date, timedelta

# ---------------- Date helpers ----------------


def default_window():
    today = date.today()
    return today - timedelta(days=7), today


# ---------------- Columns / formatting helpers ----------------

NUMERIC_COLS = [
    "money_spent",
    "money_spent_per_day",
    "orders_money_ads",
    "views",
    "views_per_day",
    "clicks",
    "clicks_per_day",
    "click_price",
    "rpc",
    "target_cpc",
    "vpo",
    "total_revenue",
    "total_revenue_per_day",
    "ordered_units",
    "ordered_units_per_day",
    "bid",
    "total_drr_pct",
    "total_drr",
    "total_drr_after_chng",
    "ctr",
    "cr",
    "vor",
    "cpm",
    "organic_pct",
]

MONEY_COLS = {"money_spent", "money_spent_per_day", "orders_money_ads", "click_price", "rpc", "target_cpc", "total_revenue", "total_revenue_per_day", "cpm", "bid"}
PCT_COLS = {"ctr", "cr", "vor", "organic_pct", "total_drr_pct", "total_drr", "total_drr_after_chng"}


def to_num_series(s: pd.Series) -> pd.Series:
    return (
        s.astype(str)
        .str.replace(" ", "", regex=False)
        .str.replace(",", ".", regex=False)
        .pipe(pd.to_numeric, errors="coerce")
        .fillna(0.0)
    )


def make_view_df(df_in: pd.DataFrame) -> pd.DataFrame:
    """
    Р”РµСЂР¶РёРј Р·РЅР°С‡РµРЅРёСЏ Р§РРЎР›РђРњР (С‡С‚РѕР±С‹ СЃРѕСЂС‚РёСЂРѕРІРєР° Р±С‹Р»Р° С‡РёСЃР»РѕРІРѕР№),
    С„РѕСЂРјР°С‚РёСЂСѓРµРј РІ UI С‡РµСЂРµР· column_config РёР»Рё С‡РµСЂРµР· Styler.format.
    """
    df_out = df_in.copy()

    for c in NUMERIC_COLS:
        if c not in df_out.columns:
            continue

        s = to_num_series(df_out[c])

        if c in PCT_COLS:
            df_out[c] = s.round(1)
        elif c in {"click_price", "rpc", "target_cpc", "vpo", "bid"}:
            df_out[c] = s.round(1)  # С‚СЂРµР±РѕРІР°РЅРёРµ: 1 Р·РЅР°Рє РїРѕСЃР»Рµ Р·Р°РїСЏС‚РѕР№
        else:
            df_out[c] = s.round(0)

    df_out = df_out.drop(columns=[c for c in df_out.columns if c.endswith("__num")], errors="ignore")
    return df_out


def format_date_ddmmyyyy(s: pd.Series) -> pd.Series:
    dt = pd.to_datetime(s, errors="coerce")
    return dt.dt.strftime("%d.%m.%Y").fillna(s.astype(str))


def build_column_config(df: pd.DataFrame) -> dict:
    cfg: dict = {}

    # money
    for col in MONEY_COLS:
        if col not in df.columns:
            continue
        if col in {"click_price", "rpc", "target_cpc", "bid"}:
            label = "CPC ????" if col == "click_price" else col
            cfg[col] = st.column_config.NumberColumn(col, format="%.1f ₽")
        else:
            cfg[col] = st.column_config.NumberColumn(col, format="%.0f ₽")

    # pct
    for col in PCT_COLS:
        if col in df.columns:
            cfg[col] = st.column_config.NumberColumn(col, format="%.1f%%")

    # ints
    for col in ("views", "views_per_day", "clicks", "clicks_per_day", "ordered_units", "ordered_units_per_day"):
        if col in df.columns:
            cfg[col] = st.column_config.NumberColumn(col, format="%.0f")

    if "vpo" in df.columns:
        cfg["vpo"] = st.column_config.NumberColumn("vpo", format="%.1f")

    if "strategy_updated_at" in df.columns:
        cfg["strategy_updated_at"] = st.column_config.TextColumn("дата последнего изменения стратегии")

    if "cpc_econ_range" in df.columns:
        cfg["cpc_econ_range"] = st.column_config.TextColumn("CPC econ")

    return cfg


def fmt_int_space(x: float) -> str:
    try:
        v = int(round(float(x)))
        return f"{v:,}".replace(",", " ")
    except Exception:
        return "0"


def fmt_rub_space(x: float) -> str:
    try:
        v = float(x)
    except Exception:
        v = 0.0
    return f"{fmt_int_space(v)} ₽"


def fmt_rub_1(x: float) -> str:
    try:
        return f"{float(x):,.1f}".replace(",", " ").replace(".", ",") + " ₽"
    except Exception:
        return "0,0 ₽"


def fmt_pct_1(x: float) -> str:
    try:
        return f"{float(x):.1f}%"
    except Exception:
        return "0.0%"


def build_download_bytes(df: pd.DataFrame) -> bytes:
    cols = list(df.columns)
    out = (";".join(cols) + "\n").encode("utf-8")
    for _, r in df.iterrows():
        line = ";".join("" if pd.isna(r[c]) else str(r[c]) for c in cols) + "\n"
        out += line.encode("utf-8")
    return out

