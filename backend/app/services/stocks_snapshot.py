from __future__ import annotations

import logging
from time import perf_counter
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pandas as pd
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.models.campaign import Campaign, CampaignDailyMetric, CampaignProduct
from app.models.organization import Organization
from app.services.company_config import resolve_company_config
from app.services.legacy_compat import (
    build_stocks_rows,
    build_stocks_rows_cached,
)
from app.services.shipment_history import (
    has_unknown_shipment_city,
    load_shipment_events_map,
    load_shipment_pairs,
    load_shipment_transit_map,
    rebuild_shipment_history_from_api,
)

logger = logging.getLogger("uvicorn.error")
MOSCOW_TZ = ZoneInfo("Europe/Moscow")


TRANSIT_DAYS_MAP = {
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

WAREHOUSE_CITY_PREFIXES = (
    ("МОСКВА", ("ХОРУГВИНО", "НОГИНСК", "ПУШКИНО", "СОФЬИНО", "РАДУМЛЯ", "ПАВЛО", "ПЕТРОВСКОЕ", "ЖУКОВСКИЙ", "ДОМОДЕДОВО", "ГРИВНО", "ВАТУТИНКИ")),
    ("ТВЕРЬ", ("ТВЕРЬ",)),
    ("ЯРОСЛАВЛЬ", ("ЯРОСЛАВЛЬ",)),
    ("САНКТ-ПЕТЕРБУРГ", ("СПБ", "САНКТ-ПЕТЕРБУРГ", "КОЛПИНО", "ШУШАРЫ", "ВОЛХОНКА", "БУГРЫ")),
    ("КАЗАНЬ", ("КАЗАНЬ", "КЗН", "НИЖНИЙ НОВГОРОД")),
    ("САМАРА", ("САМАРА",)),
    ("САРАТОВ", ("САРАТОВ", "ВОЛГОГРАД")),
    ("УФА", ("УФА",)),
    ("ОРЕНБУРГ", ("ОРЕНБУРГ",)),
    ("КРАСНОДАР", ("АДЫГЕЙСК", "ЮЖНЫЙ ОБХОД", "НОВОРОССИЙСК")),
    ("РОСТОВ", ("РОСТОВ",)),
    ("ВОРОНЕЖ", ("ВОРОНЕЖ",)),
    ("НЕВИННОМЫССК", ("НЕВИННОМЫССК",)),
    ("МАХАЧКАЛА", ("МАХАЧКАЛА",)),
    ("КРАСНОЯРСК", ("КРАСНОЯРСК",)),
    ("НОВОСИБИРСК", ("НОВОСИБИРСК", "КЕМЕРОВО")),
    ("ОМСК", ("ОМСК",)),
    ("ЕКАТЕРИНБУРГ", ("ЕКАТЕРИНБУРГ",)),
    ("ПЕРМЬ", ("ПЕРМЬ",)),
    ("ТЮМЕНЬ", ("ТЮМЕНЬ",)),
    ("ДАЛЬНИЙ", ("ХАБАРОВСК",)),
    ("КАЛИНИНГРАД", ("КАЛИНИНГРАД",)),
    ("БЕЛАРУСЬ", ("МИНСК",)),
    ("АСТАНА", ("АСТАНА",)),
    ("АЛМАТЫ", ("АЛМАТЫ",)),
    ("АРМЕНИЯ", ("ЕРЕВАН",)),
)


def _normalize_city(value: str) -> str:
    text = str(value or "").strip().upper().replace("Ё", "Е")
    if not text:
        return "UNKNOWN"
    compact = text.replace(" ", "").replace("-", "").replace("_", "")
    if (
        compact.startswith("СПБ")
        or compact.startswith("SPB")
        or "САНКТПЕТЕРБУРГ" in compact
        or "SAINTPETERSBURG" in compact
        or "STPETERSBURG" in compact
    ):
        return "САНКТ-ПЕТЕРБУРГ"
    if "МОСКВА" in text or "МО И ДАЛЬНИЕ РЕГИОНЫ" in text or "МО И ДАЛ" in text:
        return "МОСКВА"
    if "САНКТ-ПЕТЕРБУРГ" in text or "СЗО" in text:
        return "САНКТ-ПЕТЕРБУРГ"
    if "ХАБАРОВСК" in text:
        return "ДАЛЬНИЙ"
    if "РОСТОВ-НА-ДОНУ" in text or "ROSTOVONDON" in compact:
        return "РОСТОВ"
    for city_key, prefixes in WAREHOUSE_CITY_PREFIXES:
        if any(text.startswith(prefix) for prefix in prefixes):
            return city_key
    for suffix in ("_РФЦ_НОВЫЙ", "_МРФЦ", "_РФЦ", "_РЦ"):
        if text.endswith(suffix):
            text = text[: -len(suffix)]
            break
    text = text.replace("_1", "").replace("_2", "").strip("_ ").strip()
    return text or "UNKNOWN"


def _is_moscow_or_spb(cluster_name: str) -> bool:
    text = str(cluster_name or "").strip().lower()
    return any(
        token in text
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


def _city_key_to_label(city_key: str) -> str:
    text = str(city_key or "").strip()
    if not text:
        return "UNKNOWN"
    return "-".join(part.capitalize() for part in text.split("-"))


def _format_cache_ts(value: datetime | None, *, naive_tz) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=naive_tz)
    return value.isoformat()


def _position_filter_rows(rows: list[dict], position_filter: str) -> list[dict]:
    if position_filter == "ALL":
        return rows
    out: list[dict] = []
    for row in rows:
        offer_id = str(row.get("offer_id") or "").upper()
        is_additional = "AURA" in offer_id
        if position_filter == "ADDITIONAL" and is_additional:
            out.append(row)
        if position_filter == "CORE" and not is_additional:
            out.append(row)
    return out


def _build_shipments_lookup(
    seller_client_id: str,
    *,
    company_name: str,
    db: Session | None,
) -> tuple[set[tuple[str, str]], datetime | None]:
    if db is None:
        return set(), None
    pairs, ts = load_shipment_pairs(
        db,
        company_name=company_name,
        seller_client_id=seller_client_id,
    )
    return pairs, ts


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value)).date()
    except ValueError:
        return None


def _build_article_drr_lookup(
    db: Session | None,
    *,
    company_name: str,
    date_from: str | None,
    date_to: str | None,
    sku_article_map: dict[str, str],
) -> dict[str, float | None]:
    if db is None or not sku_article_map:
        return {}

    start = _parse_date(date_from)
    end = _parse_date(date_to)
    if start is None or end is None:
        return {}
    if start > end:
        start, end = end, start

    organization = (
        db.query(Organization)
        .filter(or_(Organization.slug == company_name, Organization.name == company_name))
        .first()
    )
    if organization is None:
        return {}

    campaign_skus: dict[int, set[str]] = {}
    product_rows = (
        db.query(CampaignProduct.campaign_id, CampaignProduct.sku)
        .join(Campaign, Campaign.id == CampaignProduct.campaign_id)
        .filter(Campaign.organization_id == organization.id)
        .all()
    )
    for campaign_id, sku in product_rows:
        sku_text = str(sku or "").strip()
        if not sku_text:
            continue
        campaign_skus.setdefault(int(campaign_id), set()).add(sku_text)

    article_campaigns: dict[str, set[int]] = {}
    for campaign_id, skus in campaign_skus.items():
        if len(skus) != 1:
            continue
        sku = next(iter(skus))
        article = sku_article_map.get(sku)
        if article:
            article_campaigns.setdefault(article, set()).add(campaign_id)

    candidate_campaign_ids = sorted(
        {
            next(iter(campaign_ids))
            for campaign_ids in article_campaigns.values()
            if len(campaign_ids) == 1
        }
    )
    if not candidate_campaign_ids:
        return {article: None for article in article_campaigns}

    metric_rows = (
        db.query(
            CampaignDailyMetric.campaign_id,
            func.sum(CampaignDailyMetric.money_spent),
            func.sum(CampaignDailyMetric.total_revenue),
        )
        .filter(CampaignDailyMetric.campaign_id.in_(candidate_campaign_ids))
        .filter(CampaignDailyMetric.day >= start, CampaignDailyMetric.day <= end)
        .group_by(CampaignDailyMetric.campaign_id)
        .all()
    )
    metrics_by_campaign = {
        int(campaign_id): (float(spend or 0.0), float(revenue or 0.0))
        for campaign_id, spend, revenue in metric_rows
    }

    drr_by_article: dict[str, float | None] = {}
    for article, campaign_ids in article_campaigns.items():
        if len(campaign_ids) != 1:
            drr_by_article[article] = None
            continue
        campaign_id = next(iter(campaign_ids))
        spend, revenue = metrics_by_campaign.get(campaign_id, (0.0, 0.0))
        if revenue <= 0:
            drr_by_article[article] = None
        else:
            drr_by_article[article] = round(spend / revenue * 100.0, 1)
    return drr_by_article


def get_stocks_snapshot(*, company: str | None = None) -> dict:
    company_name, config = resolve_company_config(company)
    seller_client_id = (config.get("seller_client_id") or "").strip()
    seller_api_key = (config.get("seller_api_key") or "").strip()

    if not seller_client_id or not seller_api_key:
        return {
            "company": company_name,
            "seller_client_id": seller_client_id,
            "rows": [],
            "sku_count": 0,
        }

    rows, sku_count = build_stocks_rows(
        seller_client_id=seller_client_id,
        seller_api_key=seller_api_key,
    )

    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.sort_values(["article", "cluster"], ascending=[True, True]).reset_index(drop=True)

    return {
        "company": company_name,
        "seller_client_id": seller_client_id,
        "rows": df.to_dict("records") if not df.empty else [],
        "sku_count": sku_count,
    }


def get_stocks_workspace(
    *,
    company: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    regional_order_min: int = 2,
    regional_order_target: int = 5,
    position_filter: str = "ALL",
    force_refresh: bool = False,
    db: Session | None = None,
) -> dict:
    started_at = perf_counter()
    timings: dict[str, float] = {}

    def mark(key: str, checkpoint: float) -> float:
        now = perf_counter()
        timings[key] = round((now - checkpoint) * 1000, 2)
        return now

    checkpoint = perf_counter()
    company_name, config = resolve_company_config(company)
    checkpoint = mark("resolve_company_ms", checkpoint)
    seller_client_id = (config.get("seller_client_id") or "").strip()
    seller_api_key = (config.get("seller_api_key") or "").strip()

    normalized_position_filter = str(position_filter or "ALL").upper()
    if normalized_position_filter not in {"ALL", "CORE", "ADDITIONAL"}:
        normalized_position_filter = "ALL"

    regional_order_min = max(0, int(regional_order_min or 0))
    regional_order_target = max(regional_order_min, int(regional_order_target or 0))

    if not seller_client_id or not seller_api_key:
        return {
            "company": company_name,
            "seller_client_id": seller_client_id,
            "sku_count": 0,
            "stocks_updated_at": None,
            "shipments_updated_at": None,
            "settings": {
                "regional_order_min": regional_order_min,
                "regional_order_target": regional_order_target,
                "position_filter": normalized_position_filter,
            },
            "summary": {
                "article_count": 0,
                "city_count": 0,
                "candidate_count": 0,
                "approved_count": 0,
            },
            "timings": {**timings, "total_ms": round((perf_counter() - started_at) * 1000, 2)},
            "columns": [],
            "rows": [],
        }

    checkpoint = perf_counter()
    base_rows, sku_count, stocks_ts = build_stocks_rows_cached(
        seller_client_id=seller_client_id,
        seller_api_key=seller_api_key,
        max_age_hours=0 if force_refresh else 24,
    )
    checkpoint = mark("stocks_cache_ms", checkpoint)
    filtered_rows = _position_filter_rows(base_rows, normalized_position_filter)

    if force_refresh and db is not None:
        try:
            rebuild_checkpoint = perf_counter()
            rebuild_shipment_history_from_api(
                db,
                company_name=company_name,
                seller_client_id=seller_client_id,
                seller_api_key=seller_api_key,
            )
            timings["shipment_rebuild_ms"] = round((perf_counter() - rebuild_checkpoint) * 1000, 2)
        except Exception:
            logger.exception("stocks workspace forced shipment rebuild failed", extra={"company": company_name})

    checkpoint = perf_counter()
    shipments_pairs, shipments_ts = _build_shipments_lookup(
        seller_client_id,
        company_name=company_name,
        db=db,
    )
    checkpoint = mark("shipment_pairs_ms", checkpoint)
    if db is not None and not shipments_pairs:
        try:
            rebuild_checkpoint = perf_counter()
            rebuild_shipment_history_from_api(
                db,
                company_name=company_name,
                seller_client_id=seller_client_id,
                seller_api_key=seller_api_key,
            )
            timings["shipment_rebuild_ms"] = round((perf_counter() - rebuild_checkpoint) * 1000, 2)
            shipments_pairs, shipments_ts = _build_shipments_lookup(
                seller_client_id,
                company_name=company_name,
                db=db,
            )
        except Exception:
            logger.exception("stocks workspace shipment rebuild failed", extra={"company": company_name})
            shipments_pairs, shipments_ts = set(), None
    else:
        timings.setdefault("shipment_rebuild_ms", 0)

    checkpoint = perf_counter()
    df = pd.DataFrame(filtered_rows)
    if df.empty:
        timings["dataframe_ms"] = round((perf_counter() - checkpoint) * 1000, 2)
        timings["total_ms"] = round((perf_counter() - started_at) * 1000, 2)
        logger.info(
            "stocks workspace built company=%s rows=%s columns=%s timings=%s",
            company_name,
            0,
            0,
            timings,
        )
        return {
            "company": company_name,
            "seller_client_id": seller_client_id,
            "sku_count": sku_count,
            "stocks_updated_at": _format_cache_ts(stocks_ts, naive_tz=MOSCOW_TZ),
            "shipments_updated_at": _format_cache_ts(shipments_ts, naive_tz=timezone.utc),
            "settings": {
                "regional_order_min": regional_order_min,
                "regional_order_target": regional_order_target,
                "position_filter": normalized_position_filter,
            },
            "summary": {
                "article_count": 0,
                "city_count": 0,
                "candidate_count": 0,
                "approved_count": 0,
            },
            "timings": timings,
            "columns": [],
            "rows": [],
        }

    if "article" not in df.columns:
        if "offer_id" in df.columns:
            df["article"] = df["offer_id"].astype(str)
        else:
            df["article"] = df.get("sku", "").astype(str)
    df["article"] = df["article"].fillna("").astype(str)
    if "sku" in df.columns:
        df.loc[df["article"].str.strip() == "", "article"] = df["sku"].astype(str)

    article_title_map = (
        df.groupby("article")["title"].agg(lambda values: next((str(item) for item in values if str(item).strip()), "")).to_dict()
        if "title" in df.columns
        else {}
    )
    sku_article_map: dict[str, str] = {}
    if "sku" in df.columns:
        sku_article_options: dict[str, set[str]] = {}
        for _, item in df[["sku", "article"]].dropna().iterrows():
            sku_text = str(item.get("sku") or "").strip()
            article_text = str(item.get("article") or "").strip()
            if sku_text and article_text:
                sku_article_options.setdefault(sku_text, set()).add(article_text)
        sku_article_map = {
            sku: next(iter(articles))
            for sku, articles in sku_article_options.items()
            if len(articles) == 1
        }
    article_drr_map = _build_article_drr_lookup(
        db,
        company_name=company_name,
        date_from=date_from,
        date_to=date_to,
        sku_article_map=sku_article_map,
    )

    df_pivot = df.pivot_table(index="article", columns="cluster", values="available_stock_count", aggfunc="sum").sort_index()
    df_ads = df.pivot_table(index="article", columns="cluster", values="ads_cluster", aggfunc="mean").reindex_like(df_pivot)
    df_transit = df.pivot_table(index="article", columns="cluster", values="transit_stock_count", aggfunc="sum").reindex_like(df_pivot)
    grade_map = df.pivot_table(
        index="article",
        columns="cluster",
        values="turnover_grade",
        aggfunc=lambda values: next((str(item) for item in values if item), ""),
    ).reindex_like(df_pivot)

    transit_lookup = load_shipment_transit_map(
        db,
        company_name=company_name,
        seller_client_id=seller_client_id,
        articles={str(article) for article in df_pivot.index.astype(str).tolist()},
    )
    use_supply_transit = db is not None and shipments_ts is not None

    transit_for_totals = pd.DataFrame(0, index=df_pivot.index, columns=df_pivot.columns) if use_supply_transit else df_transit.fillna(0)
    cluster_totals = df_pivot.fillna(0).sum(axis=0) + transit_for_totals.sum(axis=0)
    ordered_clusters = cluster_totals.sort_values(ascending=False).index.astype(str).tolist()
    existing_city_keys = {_normalize_city(str(city)) for city in ordered_clusters}
    transit_city_keys = {city_key for (_article, city_key), qty in transit_lookup.items() if int(qty or 0) > 0}
    for city_key in sorted(transit_city_keys - existing_city_keys):
        ordered_clusters.append(_city_key_to_label(city_key))
    if has_unknown_shipment_city(
        db,
        company_name=company_name,
        seller_client_id=seller_client_id,
    ) and "UNKNOWN" not in {_normalize_city(str(city)) for city in ordered_clusters}:
        ordered_clusters.append("UNKNOWN")

    df_pivot = df_pivot.reindex(columns=ordered_clusters).loc[:, lambda frame: ~frame.columns.duplicated()]
    df_ads = df_ads.reindex(columns=ordered_clusters).loc[:, lambda frame: ~frame.columns.duplicated()]
    df_transit = df_transit.reindex(columns=ordered_clusters).loc[:, lambda frame: ~frame.columns.duplicated()]
    grade_map = grade_map.reindex(columns=ordered_clusters).loc[:, lambda frame: ~frame.columns.duplicated()]

    stock = df_pivot.fillna(0)
    transit = df_transit.fillna(0)
    total_with_transit = stock + transit
    need60 = df_ads.fillna(0) * 60.0

    if use_supply_transit:
        transit.loc[:, :] = 0
        for article in stock.index.astype(str).tolist():
            for city in stock.columns.astype(str).tolist():
                city_key = _normalize_city(str(city))
                supply_transit_qty = int(transit_lookup.get((article, city_key), 0) or 0)
                transit.at[article, city] = supply_transit_qty
        total_with_transit = stock + transit
    elif transit_lookup:
        for article in stock.index.astype(str).tolist():
            for city in stock.columns.astype(str).tolist():
                city_key = _normalize_city(str(city))
                supply_transit_qty = int(transit_lookup.get((article, city_key), 0) or 0)
                if supply_transit_qty > float(transit.at[article, city]):
                    transit.at[article, city] = supply_transit_qty
        total_with_transit = stock + transit

    for column in need60.columns:
        days = TRANSIT_DAYS_MAP.get(str(column).strip().lower(), 0)
        if days:
            need60[column] = need60[column] * (1.0 + (days / 60.0))

    candidate_mask = pd.DataFrame(False, index=stock.index, columns=stock.columns)
    for column in candidate_mask.columns:
        city_key = _normalize_city(str(column))
        if _is_moscow_or_spb(str(column)):
            candidate_mask[column] = total_with_transit[column] <= need60[column]
        else:
            candidate_mask[column] = total_with_transit[column] <= float(regional_order_min)
        candidate_mask[column] = candidate_mask[column] & pd.Series(
            [(str(article), city_key) in shipments_pairs for article in candidate_mask.index],
            index=candidate_mask.index,
        )
    checkpoint = mark("dataframe_ms", checkpoint)

    events_checkpoint = perf_counter()
    shipment_events_by_cell = load_shipment_events_map(
        db,
        company_name=company_name,
        seller_client_id=seller_client_id,
        articles={str(article) for article in stock.index.astype(str).tolist()},
        city_keys={_normalize_city(str(city)) for city in stock.columns.astype(str).tolist()},
        per_cell_limit=6,
    )
    timings["shipment_events_ms"] = round((perf_counter() - events_checkpoint) * 1000, 2)

    matrix_checkpoint = perf_counter()
    matrix_rows: list[dict] = []
    candidate_count = 0
    now_utc = datetime.utcnow()
    soon_30_cutoff = now_utc + timedelta(days=30)
    soon_60_cutoff = now_utc + timedelta(days=60)
    for article in stock.index.astype(str).tolist():
        cells: list[dict] = []
        for city in stock.columns.astype(str).tolist():
            city_key = _normalize_city(str(city))
            stock_value = int(round(float(stock.at[article, city])))
            need60_value = int(round(float(need60.at[article, city])))
            in_transit_value = int(round(float(transit.at[article, city])))
            total_value = int(round(float(total_with_transit.at[article, city])))
            is_candidate = bool(candidate_mask.at[article, city])
            shipment_meta = shipment_events_by_cell.get((article, city_key), {})
            events = shipment_meta.get("events") or []
            events_for_calc = shipment_meta.get("events_for_calc") or events
            remaining_stock = max(0, stock_value)
            shipment_events = []
            paid_storage_qty = 0
            paid_storage_soon_30_qty = 0
            paid_storage_soon_60_qty = 0
            for item in events_for_calc:
                qty = int(item.get("quantity") or 0)
                event_at = item.get("event_at")
                unsold_qty = min(qty, remaining_stock)
                remaining_stock = max(0, remaining_stock - unsold_qty)
                free_storage_until = event_at + timedelta(days=120) if (event_at and unsold_qty > 0) else None
                paid_qty = int(unsold_qty) if (free_storage_until is not None and free_storage_until <= now_utc) else 0
                if paid_qty > 0:
                    paid_storage_qty += paid_qty
                elif free_storage_until is not None and unsold_qty > 0:
                    if free_storage_until <= soon_30_cutoff:
                        paid_storage_soon_30_qty += int(unsold_qty)
                    if free_storage_until <= soon_60_cutoff:
                        paid_storage_soon_60_qty += int(unsold_qty)
            remaining_stock = max(0, stock_value)
            for item in events:
                qty = int(item.get("quantity") or 0)
                event_at = item.get("event_at")
                unsold_qty = min(qty, remaining_stock)
                remaining_stock = max(0, remaining_stock - unsold_qty)
                free_storage_until = event_at + timedelta(days=120) if (event_at and unsold_qty > 0) else None
                paid_qty = int(unsold_qty) if (free_storage_until is not None and free_storage_until <= now_utc) else 0
                shipment_events.append(
                    {
                        "quantity": qty,
                        "event_at": event_at.isoformat() if event_at else None,
                        "unsold_qty": int(unsold_qty),
                        "free_storage_until": free_storage_until.isoformat() if free_storage_until else None,
                        "paid_qty": paid_qty,
                    }
                )
            if is_candidate:
                candidate_count += 1
            cells.append(
                {
                    "city": city,
                    "stock": stock_value,
                    "need60": need60_value,
                    "in_transit": in_transit_value,
                    "total_with_transit": total_value,
                    "turnover_grade": str(grade_map.at[article, city] or ""),
                    "is_candidate": is_candidate,
                    "display_value": f"{stock_value} | {need60_value} | {in_transit_value}",
                    "shipment_total_qty": int(shipment_meta.get("total_quantity") or 0),
                    "shipment_events_count": int(shipment_meta.get("events_count") or 0),
                    "shipment_last_at": shipment_meta.get("last_event_at").isoformat()
                    if shipment_meta.get("last_event_at")
                    else None,
                    "paid_storage_qty": paid_storage_qty,
                    "paid_storage_soon_30_qty": paid_storage_soon_30_qty,
                    "paid_storage_soon_60_qty": paid_storage_soon_60_qty,
                    "shipment_events": shipment_events,
                }
            )
        matrix_rows.append(
            {
                "article": article,
                "title": article_title_map.get(article, ""),
                "drr_pct": article_drr_map.get(article),
                "cells": cells,
            }
        )
    timings["matrix_ms"] = round((perf_counter() - matrix_checkpoint) * 1000, 2)
    timings["total_ms"] = round((perf_counter() - started_at) * 1000, 2)
    logger.info(
        "stocks workspace built company=%s rows=%s columns=%s timings=%s",
        company_name,
        len(matrix_rows),
        len(ordered_clusters),
        timings,
    )

    return {
        "company": company_name,
        "seller_client_id": seller_client_id,
        "sku_count": sku_count,
        "stocks_updated_at": _format_cache_ts(stocks_ts, naive_tz=MOSCOW_TZ),
        "shipments_updated_at": _format_cache_ts(shipments_ts, naive_tz=timezone.utc),
        "settings": {
            "regional_order_min": regional_order_min,
            "regional_order_target": regional_order_target,
            "position_filter": normalized_position_filter,
        },
        "summary": {
            "article_count": len(matrix_rows),
            "city_count": len(ordered_clusters),
            "candidate_count": candidate_count,
            "approved_count": 0,
        },
        "timings": timings,
        "columns": ordered_clusters,
        "rows": matrix_rows,
    }
