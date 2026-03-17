# -*- coding: utf-8 -*-
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import timedelta, datetime, date
import pandas as pd
import streamlit as st

from clients_ads import (
    perf_token,
    get_campaigns,
    get_campaign_products_all,
    get_campaign_stats_json,
)
from clients_seller import seller_analytics_sku_day
from report import chunks, campaign_display_fields
from ui_formatting import fmt_rub_1


def daterange(date_from: date, date_to: date):
    d = date_from
    while d <= date_to:
        yield d
        d += timedelta(days=1)


def rub_to_api_bid_micro(rub_value: float) -> int:
    return int(round(float(rub_value) * 1_000_000))


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


def _to_int_round(value) -> int:
    try:
        return int(round(_to_num(value)))
    except Exception:
        return 0


def _load_products_parallel(token: str, campaign_ids: list[str], page_size: int = 100) -> dict[str, list[dict]]:
    if not campaign_ids:
        return {}

    out: dict[str, list[dict]] = {str(cid): [] for cid in campaign_ids}
    max_workers = min(4, max(1, len(campaign_ids)))

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_map = {
            executor.submit(get_campaign_products_all, token, str(cid), page_size): str(cid)
            for cid in campaign_ids
        }
        for future in as_completed(future_map):
            cid = future_map[future]
            out[cid] = future.result()

    return out


@st.cache_data(show_spinner=False, ttl=300)
def fetch_running_campaigns_cached(perf_client_id: str | None = None, perf_client_secret: str | None = None):
    token = perf_token(client_id=perf_client_id, client_secret=perf_client_secret)
    campaigns = get_campaigns(token)
    running = [c for c in campaigns if c.get("state") == "CAMPAIGN_STATE_RUNNING"]
    running.sort(key=lambda x: (x.get("title") or "").lower())
    return running


def fetch_ads_stats_by_campaign(token: str, date_from: str, date_to: str, running_ids: list[str], batch_size: int):
    """
    Р—Р°Р±РёСЂР°РµРј stats РїРѕ РєР°РјРїР°РЅРёСЏРј Р·Р° РїРµСЂРёРѕРґ Р±Р°С‚С‡Р°РјРё: get_campaign_stats_json(..., campaign_ids=[...]).
    Р’РѕР·РІСЂР°С‰Р°РµРј dict campaign_id -> stats_row.
    """
    stats_by_campaign_id: dict[str, dict] = {}
    for batch in chunks(running_ids, int(batch_size)):
        stats = get_campaign_stats_json(token, date_from, date_to, batch)
        rows = stats.get("rows", []) or []
        for r in rows:
            stats_by_campaign_id[str(r.get("id"))] = r
    return stats_by_campaign_id


@st.cache_data(show_spinner=False, ttl=300)
def fetch_ads_stats_by_campaign_cached(
    perf_client_id: str | None,
    perf_client_secret: str | None,
    date_from: str,
    date_to: str,
    running_ids: list[str],
    batch_size: int,
):
    token = perf_token(client_id=perf_client_id, client_secret=perf_client_secret)
    return fetch_ads_stats_by_campaign(token, date_from, date_to, running_ids, batch_size)


def fetch_ads_daily_totals(
    token: str,
    date_from: str,
    date_to: str,
    running_ids: list[str],
    batch_size: int,
    return_by_campaign: bool = False,
):
    """
    РС‚РѕРіРё Ads РїРѕ РґРЅСЏРј (Р±РµР· Seller): moneySpent/views/clicks/ordersMoney СЃРѕР±РёСЂР°РµРј РїРѕ РІСЃРµРј running campaigns.
    Seller-С‡Р°СЃС‚СЊ (revenue/units) РґРѕР±Р°РІРёРј РѕС‚РґРµР»СЊРЅРѕ.
    """
    d_from = datetime.fromisoformat(date_from).date()
    d_to = datetime.fromisoformat(date_to).date()
    days = [d.isoformat() for d in daterange(d_from, d_to)]

    out = []
    by_campaign_day = {} if return_by_campaign else None
    for day_str in days:
        day_spend = 0.0
        day_views = 0
        day_clicks = 0
        day_orders_money = 0.0
        day_orders = 0

        for batch in chunks(running_ids, int(batch_size)):
            stats_day = get_campaign_stats_json(token, day_str, day_str, batch)
            for r in (stats_day.get("rows", []) or []):
                spend = _to_num(r.get("moneySpent", 0))
                views = _to_int_round(r.get("views", 0))
                clicks = _to_int_round(r.get("clicks", 0))
                orders_money = _to_num(r.get("ordersMoney", 0))
                orders = _to_int_round(r.get("orders", 0))
                click_price_api = _to_num(r.get("clickPrice", 0))
                click_price = (spend / clicks) if clicks > 0 else click_price_api

                day_spend += spend
                day_views += views
                day_clicks += clicks
                day_orders_money += orders_money
                day_orders += orders

                if return_by_campaign:
                    cid = str(r.get("id"))
                    by_campaign_day[(day_str, cid)] = {
                        "money_spent": float(spend),
                        "views": views,
                        "clicks": clicks,
                        "click_price": float(click_price),
                        "orders_money_ads": float(orders_money),
                        "orders": orders,
                    }

        out.append(
            {
                "day": day_str,
                "views": day_views,
                "clicks": day_clicks,
                "money_spent": float(day_spend),
                "orders_money_ads": float(day_orders_money),
                "orders": int(day_orders),  # РІРЅСѓС‚СЂРµРЅРЅРµРµ РїРѕР»Рµ
            }
        )
    if return_by_campaign:
        return out, by_campaign_day
    return out


@st.cache_data(show_spinner=False, ttl=300)
def fetch_ads_daily_totals_cached(
    perf_client_id: str | None,
    perf_client_secret: str | None,
    date_from: str,
    date_to: str,
    running_ids: list[str],
    batch_size: int,
    return_by_campaign: bool = False,
):
    token = perf_token(client_id=perf_client_id, client_secret=perf_client_secret)
    return fetch_ads_daily_totals(
        token,
        date_from,
        date_to,
        running_ids,
        batch_size,
        return_by_campaign=return_by_campaign,
    )


def build_campaign_daily_rows_cached(
    campaign_id: str,
    date_from: str,
    date_to: str,
    seller_by_day_sku: dict,
    ads_daily_by_campaign: dict,
    target_drr: float = 0.2,
    items: list[dict] | None = None,
):
    items = items or []
    out_sku, out_title, _out_bid, skus = campaign_display_fields("", items)

    d_from = datetime.fromisoformat(date_from).date()
    d_to = datetime.fromisoformat(date_to).date()
    days = [d.isoformat() for d in daterange(d_from, d_to)]

    out: list[dict] = []
    for day_str in days:
        stats = ads_daily_by_campaign.get((day_str, str(campaign_id)), {})

        money_spent = float(stats.get("money_spent", 0.0) or 0.0)
        views = int(stats.get("views", 0) or 0)
        clicks = int(stats.get("clicks", 0) or 0)
        click_price = float(stats.get("click_price", 0.0) or 0.0)
        orders = int(stats.get("orders", 0) or 0)
        orders_money_ads = float(stats.get("orders_money_ads", 0.0) or 0.0)

        total_revenue = 0.0
        total_units = 0
        for sku in skus:
            rv, un = seller_by_day_sku.get((day_str, str(sku)), (0.0, 0))
            total_revenue += float(rv)
            total_units += int(un)

        total_drr_pct = (money_spent / total_revenue * 100.0) if total_revenue > 0 else 0.0
        ctr_pct = (clicks / views * 100.0) if views > 0 else 0.0
        cr_pct = (total_units / clicks * 100.0) if clicks > 0 else 0.0
        vor_pct = (total_units / views * 100.0) if views > 0 else 0.0
        cpm = (money_spent / views * 1000.0) if views > 0 else 0.0
        rpc = (total_revenue / clicks) if clicks > 0 else 0.0
        target_cpc = rpc * target_drr
        vpo = (views / total_units) if total_units > 0 else 0.0

        out.append(
            {
                "day": day_str,
                "campaign_id": str(campaign_id),
                "sku": out_sku,
                "title": out_title,
                "money_spent": money_spent,
                "views": views,
                "clicks": clicks,
                "click_price": click_price,
                "orders_money_ads": orders_money_ads,
                "cpm": round(cpm, 0),
                "total_revenue": total_revenue,
                "ordered_units": total_units,
                "total_drr_pct": round(total_drr_pct, 1),
                "ctr": round(ctr_pct, 1),
                "cr": round(cr_pct, 1),
                "vor": round(vor_pct, 1),
                "rpc": round(rpc, 1),
                "target_cpc": round(target_cpc, 1),
                "vpo": round(vpo, 1),
                "orders": orders,
            }
        )

    return out


def compute_daily_breakdown(ads_daily_rows: list[dict], seller_by_day: dict, target_drr: float = 0.2):
    """
    РЎРєР»РµРёРІР°РµРј Ads-РёС‚РѕРіРё РїРѕ РґРЅСЏРј + Seller revenue/units.
    РЎС‡РёС‚Р°РµРј DRR/CPM/CTR/Organic%.
    Organic% = 100 - (ordersMoney_ads / total_revenue * 100)
    ordersMoney_ads = GMV, Р°С‚СЂРёР±СѓС‚РёСЂРѕРІР°РЅРЅР°СЏ СЂРµРєР»Р°РјРµ (РїРѕРґРјРЅРѕР¶РµСЃС‚РІРѕ total_revenue РїРѕ SKU РІ РєР°РјРїР°РЅРёРё).
    """
    out = []
    for r in ads_daily_rows:
        day = r["day"]
        views = int(r.get("views", 0) or 0)
        clicks = int(r.get("clicks", 0) or 0)
        spend = float(r.get("money_spent", 0.0) or 0.0)
        orders_money_ads = float(r.get("orders_money_ads", 0.0) or 0.0)
        orders = int(r.get("orders", 0) or 0)

        rev, units = seller_by_day.get(day, (0.0, 0))

        drr = (spend / rev * 100.0) if rev > 0 else 0.0
        cpm = (spend / views * 1000.0) if views > 0 else 0.0
        ctr = (clicks / views * 100.0) if views > 0 else 0.0
        cr = (units / clicks * 100.0) if clicks > 0 else 0.0
        vor = (units / views * 100.0) if views > 0 else 0.0
        rpc = (rev / clicks) if clicks > 0 else 0.0
        target_cpc = rpc * target_drr
        vpo = (views / units) if units > 0 else 0.0

        ads_share = (orders_money_ads / rev * 100.0) if rev > 0 else 0.0
        organic_pct = (100.0 - ads_share) if rev > 0 else 0.0

        # Р·Р°С‰РёС‚РёРјСЃСЏ РѕС‚ СЂРµРґРєРёС… СЂР°СЃС…РѕР¶РґРµРЅРёР№/РѕРєСЂРѕРіР»РµРЅРёР№
        if organic_pct < 0:
            organic_pct = 0.0
        if organic_pct > 100:
            organic_pct = 100.0

        out.append(
            {
                "day": day,
                "views": views,
                "clicks": clicks,
                "money_spent": spend,
                "orders_money_ads": orders_money_ads,
                "total_revenue": float(rev),
                "ordered_units": int(units),
                "total_drr_pct": round(drr, 1),
                "cpm": round(cpm, 0),
                "ctr": round(ctr, 1),
                "cr": round(cr, 1),
                "vor": round(vor, 1),
                "rpc": round(rpc, 1),
                "target_cpc": round(target_cpc, 1),
                "vpo": round(vpo, 1),
                "organic_pct": round(organic_pct, 1),
            }
        )
    return out


def build_campaign_daily_rows(
    token: str,
    campaign_id: str,
    date_from: str,
    date_to: str,
    seller_by_day_sku: dict,
    target_drr: float = 0.2,
):
    """
    Р”РµС‚Р°Р»РєР° РїРѕ 1 РєР°РјРїР°РЅРёРё РїРѕ РґРЅСЏРј:
    - Ads: stats day-by-day С‡РµСЂРµР· get_campaign_stats_json(day, day, [campaign_id])
    - Seller: revenue/units Р±РµСЂС‘Рј РёР· seller_by_day_sku (Р±РµР· API!)
    """
    items = get_campaign_products_all(token, campaign_id, page_size=100)
    out_sku, out_title, _out_bid, skus = campaign_display_fields("", items)

    d_from = datetime.fromisoformat(date_from).date()
    d_to = datetime.fromisoformat(date_to).date()
    days = [d.isoformat() for d in daterange(d_from, d_to)]

    out: list[dict] = []
    for day_str in days:
        stats_day = get_campaign_stats_json(token, day_str, day_str, [campaign_id])
        rows = stats_day.get("rows", []) or []
        sr = rows[0] if rows else {}

        money_spent = _to_num(sr.get("moneySpent", 0))
        views = _to_int_round(sr.get("views", 0))
        clicks = _to_int_round(sr.get("clicks", 0))
        click_price_api = _to_num(sr.get("clickPrice", 0))
        orders = _to_int_round(sr.get("orders", 0))
        orders_money_ads = _to_num(sr.get("ordersMoney", 0))
        click_price = (money_spent / clicks) if clicks > 0 else click_price_api

        total_revenue = 0.0
        total_units = 0
        for sku in skus:
            rv, un = seller_by_day_sku.get((day_str, str(sku)), (0.0, 0))
            total_revenue += float(rv)
            total_units += int(un)

        total_drr_pct = (money_spent / total_revenue * 100.0) if total_revenue > 0 else 0.0
        ctr_pct = (clicks / views * 100.0) if views > 0 else 0.0
        cr_pct = (total_units / clicks * 100.0) if clicks > 0 else 0.0
        vor_pct = (total_units / views * 100.0) if views > 0 else 0.0
        cpm = (money_spent / views * 1000.0) if views > 0 else 0.0
        rpc = (total_revenue / clicks) if clicks > 0 else 0.0
        target_cpc = rpc * target_drr
        vpo = (views / total_units) if total_units > 0 else 0.0

        out.append(
            {
                "day": day_str,
                "campaign_id": str(campaign_id),
                "sku": out_sku,
                "title": out_title,
                "money_spent": money_spent,
                "views": views,
                "clicks": clicks,
                "click_price": click_price,
                "orders_money_ads": orders_money_ads,
                "cpm": round(cpm, 0),
                "total_revenue": total_revenue,
                "ordered_units": total_units,
                "total_drr_pct": round(total_drr_pct, 1),
                "ctr": round(ctr_pct, 1),
                "cr": round(cr_pct, 1),
                "vor": round(vor_pct, 1),
                "rpc": round(rpc, 1),
                "target_cpc": round(target_cpc, 1),
                "vpo": round(vpo, 1),
                "orders": orders,
            }
        )

    return out


def campaign_weekly_aggregate(df_camp_daily_raw: pd.DataFrame, target_drr: float = 0.2) -> pd.DataFrame:
    """
    Р“СЂСѓРїРїРёСЂСѓРµРј РґРЅРё РїРѕ РЅРµРґРµР»СЏРј (РїРѕРЅРµРґРµР»СЊРЅРёРє вЂ” РЅР°С‡Р°Р»Рѕ РЅРµРґРµР»Рё).
    Р”Р°С‚Р° РІ РІС‹РІРѕРґРµ: week_start (YYYY-MM-DD).
    Р”РѕР±Р°РІР»СЏРµРј days_in_period (СЃРєРѕР»СЊРєРѕ РґРЅРµР№ РїРѕРїР°Р»Рѕ РІ РґР°РЅРЅСѓСЋ РЅРµРґРµР»СЋ РёР· РІС‹Р±СЂР°РЅРЅРѕРіРѕ РѕРєРЅР°).
    """
    if df_camp_daily_raw.empty:
        return df_camp_daily_raw

    dfw = df_camp_daily_raw.copy()
    dfw["day"] = pd.to_datetime(dfw["day"]).dt.date
    dfw["week_start"] = dfw["day"].apply(lambda d: d - timedelta(days=d.weekday()))
    dfw["day_str"] = dfw["day"].astype(str)
    if "orders" not in dfw.columns:
        dfw["orders"] = 0
    if "orders_money_ads" not in dfw.columns:
        # Backward compatibility for cached daily rows created before orders_money_ads
        # was included in compute_daily_breakdown output.
        if "organic_pct" in dfw.columns and "total_revenue" in dfw.columns:
            rev = pd.to_numeric(dfw["total_revenue"], errors="coerce").fillna(0.0)
            org = pd.to_numeric(dfw["organic_pct"], errors="coerce").fillna(0.0).clip(lower=0.0, upper=100.0)
            dfw["orders_money_ads"] = (rev * (100.0 - org) / 100.0).fillna(0.0)
        else:
            dfw["orders_money_ads"] = 0.0
    if "ebitda" not in dfw.columns:
        dfw["ebitda"] = 0.0

    agg = (
        dfw.groupby("week_start", as_index=False)
        .agg(
            days_in_period=("day_str", "nunique"),
            money_spent=("money_spent", "sum"),
            views=("views", "sum"),
            clicks=("clicks", "sum"),
            orders=("orders", "sum"),
            orders_money_ads=("orders_money_ads", "sum"),
            total_revenue=("total_revenue", "sum"),
            ordered_units=("ordered_units", "sum"),
            ebitda=("ebitda", "sum"),
        )
        .sort_values("week_start")
    )

    # derived
    agg["click_price"] = agg.apply(lambda r: (r["money_spent"] / r["clicks"]) if r["clicks"] else 0.0, axis=1)
    agg["ctr"] = agg.apply(lambda r: (r["clicks"] / r["views"] * 100.0) if r["views"] else 0.0, axis=1)
    agg["cr"] = agg.apply(
        lambda r: (r["ordered_units"] / r["clicks"] * 100.0) if r["clicks"] else 0.0, axis=1
    )
    agg["vor"] = agg.apply(
        lambda r: (r["ordered_units"] / r["views"] * 100.0) if r["views"] else 0.0, axis=1
    )
    agg["cpm"] = agg.apply(lambda r: (r["money_spent"] / r["views"] * 1000.0) if r["views"] else 0.0, axis=1)
    agg["total_drr_pct"] = agg.apply(
        lambda r: (r["money_spent"] / r["total_revenue"] * 100.0) if r["total_revenue"] else 0.0, axis=1
    )
    agg["rpc"] = agg.apply(lambda r: (r["total_revenue"] / r["clicks"]) if r["clicks"] else 0.0, axis=1)
    agg["target_cpc"] = agg["rpc"] * target_drr
    agg["vpo"] = agg.apply(
        lambda r: (r["views"] / r["ordered_units"]) if r["ordered_units"] else 0.0, axis=1
    )
    agg["organic_pct"] = agg.apply(
        lambda r: (100.0 - (r["orders_money_ads"] / r["total_revenue"] * 100.0)) if r["total_revenue"] else 0.0,
        axis=1,
    ).clip(lower=0.0, upper=100.0)
    agg["ebitda_pct"] = agg.apply(
        lambda r: (r["ebitda"] / r["total_revenue"] * 100.0) if r["total_revenue"] else 0.0,
        axis=1,
    )

    agg = agg.rename(columns={"week_start": "week"})
    agg["week"] = agg["week"].astype(str)

    cols = [
        "week",
        "days_in_period",
        "views",
        "clicks",
        "ctr",
        "cr",
        "vor",
        "money_spent",
        "click_price",
        "cpm",
        "rpc",
        "target_cpc",
        "vpo",
        "total_revenue",
        "ordered_units",
        "total_drr_pct",
        "organic_pct",
        "ebitda",
        "ebitda_pct",
    ]
    return agg[cols]


def fetch_products_by_campaign(running: list[dict], token: str, include_products: bool) -> dict[str, list[dict]]:
    products_by_campaign_id: dict[str, list[dict]] = {}
    if include_products:
        campaign_ids = [str(c["id"]) for c in running]
        products_by_campaign_id = _load_products_parallel(token, campaign_ids, page_size=100)
    else:
        for c in running:
            products_by_campaign_id[str(c["id"])] = []
    return products_by_campaign_id


@st.cache_data(show_spinner=False, ttl=300)
def fetch_products_by_campaign_cached(
    perf_client_id: str | None,
    perf_client_secret: str | None,
    running_ids: list[str],
    include_products: bool,
) -> dict[str, list[dict]]:
    token = perf_token(client_id=perf_client_id, client_secret=perf_client_secret)
    products_by_campaign_id: dict[str, list[dict]] = {}
    if include_products:
        products_by_campaign_id = _load_products_parallel(
            token,
            [str(cid) for cid in running_ids],
            page_size=100,
        )
    else:
        for cid in running_ids:
            products_by_campaign_id[str(cid)] = []
    return products_by_campaign_id


@st.cache_data(show_spinner=False, ttl=300)
def seller_analytics_sku_day_cached(
    date_from: str,
    date_to: str,
    limit: int,
    seller_client_id: str | None,
    seller_api_key: str | None,
):
    return seller_analytics_sku_day(
        date_from,
        date_to,
        limit=limit,
        client_id=seller_client_id,
        api_key=seller_api_key,
    )


def calc_cpc_econ_only(
    df_camp_daily_raw: pd.DataFrame,
    target_drr: float,
    drr_abs_tolerance: float = 0.05,
) -> dict[str, float | None]:
    if df_camp_daily_raw is None or df_camp_daily_raw.empty:
        return {"cpc_econ": None, "cpc_econ_min": None, "cpc_econ_max": None}

    df = df_camp_daily_raw.copy()
    revenue_sum = float(pd.to_numeric(df.get("total_revenue", 0), errors="coerce").fillna(0).sum())
    orders_sum = float(pd.to_numeric(df.get("ordered_units", 0), errors="coerce").fillna(0).sum())
    clicks_sum = float(pd.to_numeric(df.get("clicks", 0), errors="coerce").fillna(0).sum())

    if revenue_sum <= 0 or orders_sum <= 0 or clicks_sum <= 0:
        return {"cpc_econ": None, "cpc_econ_min": None, "cpc_econ_max": None}

    order_value = revenue_sum / orders_sum
    cr = orders_sum / clicks_sum

    drr_min = max(0.0, target_drr - drr_abs_tolerance)
    drr_max = min(1.0, target_drr + drr_abs_tolerance)

    cpc_econ = order_value * cr * target_drr
    cpc_econ_min = order_value * cr * drr_min
    cpc_econ_max = order_value * cr * drr_max

    return {
        "cpc_econ": cpc_econ,
        "cpc_econ_min": cpc_econ_min,
        "cpc_econ_max": cpc_econ_max,
    }


def compute_cpc_econ_range_map(
    *,
    campaign_ids: list[str],
    date_from: str,
    date_to: str,
    seller_by_day_sku: dict,
    ads_daily_by_campaign: dict,
    products_by_campaign_id: dict[str, list[dict]],
    target_drr: float,
) -> tuple[dict[str, str], dict[str, tuple[float | None, float | None]]]:
    out: dict[str, str] = {}
    bounds: dict[str, tuple[float | None, float | None]] = {}
    for cid in campaign_ids:
        camp_daily = build_campaign_daily_rows_cached(
            campaign_id=str(cid),
            date_from=date_from,
            date_to=date_to,
            seller_by_day_sku=seller_by_day_sku,
            ads_daily_by_campaign=ads_daily_by_campaign,
            target_drr=target_drr,
            items=products_by_campaign_id.get(str(cid), []) or [],
        )
        df_camp = pd.DataFrame(camp_daily)
        econ = calc_cpc_econ_only(df_camp, target_drr=target_drr)
        cpc_econ_min = econ.get("cpc_econ_min")
        cpc_econ = econ.get("cpc_econ")
        cpc_econ_max = econ.get("cpc_econ_max")
        bounds[str(cid)] = (cpc_econ_min, cpc_econ_max)
        if cpc_econ_min is None and cpc_econ is None and cpc_econ_max is None:
            out[str(cid)] = ""
        else:
            out[str(cid)] = (
                f"{fmt_rub_1(cpc_econ_min) if cpc_econ_min is not None else '—'}"
                f" - {fmt_rub_1(cpc_econ) if cpc_econ is not None else '—'}"
                f" - {fmt_rub_1(cpc_econ_max) if cpc_econ_max is not None else '—'}"
            )
    return out, bounds
