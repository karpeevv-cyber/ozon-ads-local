from __future__ import annotations

from datetime import datetime

import pandas as pd
from sqlalchemy.orm import Session

from app.services.company_config import resolve_company_config
from app.services.legacy_compat import (
    build_stocks_rows,
    build_stocks_rows_cached,
    load_storage_cache_payload,
)
from app.services.shipment_history import load_shipment_pairs


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


def _normalize_city(value: str) -> str:
    text = str(value or "").strip().upper().replace("Ё", "Е")
    if not text:
        return "UNKNOWN"
    if "МОСКВА" in text or "МО И ДАЛЬНИЕ РЕГИОНЫ" in text or "МО И ДАЛ" in text:
        return "МОСКВА"
    if "САНКТ-ПЕТЕРБУРГ" in text or "СЗО" in text:
        return "САНКТ-ПЕТЕРБУРГ"
    for prefix in ("ГРИВНО", "НОГИНСК", "ПУШКИНО", "ХОРУГВИНО", "ПЕТРОВСКОЕ"):
        if text.startswith(prefix):
            return "МОСКВА"
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
    if db is not None:
        pairs, ts = load_shipment_pairs(
            db,
            company_name=company_name,
            seller_client_id=seller_client_id,
        )
        if pairs:
            return pairs, ts
    payload, ts, _source_path = load_storage_cache_payload(seller_client_id, "v12")
    lot_rows = payload.get("lot_rows", []) if isinstance(payload, dict) else []
    article_city_pairs: set[tuple[str, str]] = set()
    for lot in lot_rows:
        if not isinstance(lot, dict):
            continue
        article = str(lot.get("article") or "").strip()
        city_key = str(lot.get("city_key") or "").strip()
        if not city_key:
            city_key = _normalize_city(str(lot.get("city") or ""))
        if article and city_key:
            article_city_pairs.add((article, city_key))
    return article_city_pairs, ts if isinstance(ts, datetime) else None


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
    regional_order_min: int = 2,
    regional_order_target: int = 5,
    position_filter: str = "ALL",
    db: Session | None = None,
) -> dict:
    company_name, config = resolve_company_config(company)
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
            "columns": [],
            "rows": [],
        }

    base_rows, sku_count, stocks_ts = build_stocks_rows_cached(
        seller_client_id=seller_client_id,
        seller_api_key=seller_api_key,
    )
    filtered_rows = _position_filter_rows(base_rows, normalized_position_filter)
    shipments_pairs, shipments_ts = _build_shipments_lookup(
        seller_client_id,
        company_name=company_name,
        db=db,
    )

    df = pd.DataFrame(filtered_rows)
    if df.empty:
        return {
            "company": company_name,
            "seller_client_id": seller_client_id,
            "sku_count": sku_count,
            "stocks_updated_at": stocks_ts.isoformat() if stocks_ts else None,
            "shipments_updated_at": shipments_ts.isoformat() if shipments_ts else None,
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

    df_pivot = df.pivot_table(index="article", columns="cluster", values="available_stock_count", aggfunc="sum").sort_index()
    df_ads = df.pivot_table(index="article", columns="cluster", values="ads_cluster", aggfunc="mean").reindex_like(df_pivot)
    df_transit = df.pivot_table(index="article", columns="cluster", values="transit_stock_count", aggfunc="sum").reindex_like(df_pivot)
    grade_map = df.pivot_table(
        index="article",
        columns="cluster",
        values="turnover_grade",
        aggfunc=lambda values: next((str(item) for item in values if item), ""),
    ).reindex_like(df_pivot)

    cluster_totals = df_pivot.fillna(0).sum(axis=0) + df_transit.fillna(0).sum(axis=0)
    ordered_clusters = cluster_totals.sort_values(ascending=False).index.astype(str).tolist()

    df_pivot = df_pivot.reindex(columns=ordered_clusters).loc[:, lambda frame: ~frame.columns.duplicated()]
    df_ads = df_ads.reindex(columns=ordered_clusters).loc[:, lambda frame: ~frame.columns.duplicated()]
    df_transit = df_transit.reindex(columns=ordered_clusters).loc[:, lambda frame: ~frame.columns.duplicated()]
    grade_map = grade_map.reindex(columns=ordered_clusters).loc[:, lambda frame: ~frame.columns.duplicated()]

    stock = df_pivot.fillna(0)
    transit = df_transit.fillna(0)
    total_with_transit = stock + transit
    need60 = df_ads.fillna(0) * 60.0

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

    matrix_rows: list[dict] = []
    candidate_count = 0
    for article in stock.index.astype(str).tolist():
        cells: list[dict] = []
        for city in stock.columns.astype(str).tolist():
            stock_value = int(round(float(stock.at[article, city])))
            need60_value = int(round(float(need60.at[article, city])))
            in_transit_value = int(round(float(transit.at[article, city])))
            total_value = int(round(float(total_with_transit.at[article, city])))
            is_candidate = bool(candidate_mask.at[article, city])
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
                }
            )
        matrix_rows.append(
            {
                "article": article,
                "title": article_title_map.get(article, ""),
                "cells": cells,
            }
        )

    return {
        "company": company_name,
        "seller_client_id": seller_client_id,
        "sku_count": sku_count,
        "stocks_updated_at": stocks_ts.isoformat() if stocks_ts else None,
        "shipments_updated_at": shipments_ts.isoformat() if shipments_ts else None,
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
        "columns": ordered_clusters,
        "rows": matrix_rows,
    }
