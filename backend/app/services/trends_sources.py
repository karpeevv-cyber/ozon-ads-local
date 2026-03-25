from __future__ import annotations

from datetime import date
from functools import lru_cache
import os
import re

import pandas as pd

from app.services.integrations.ozon_seller import (
    seller_analytics_data,
    seller_product_info_list,
    seller_product_list,
    seller_product_queries_details,
)


ENABLE_QUERY_SIGNALS = os.getenv("TRENDS_ENABLE_QUERY_SIGNALS", "0").strip().lower() in {"1", "true", "yes"}


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())


@lru_cache(maxsize=32)
def _load_catalog_cached(seller_client_id: str | None, seller_api_key: str | None) -> tuple[dict, ...]:
    product_ids: list[str] = []
    last_id = ""
    seen_last_ids: set[str] = set()
    while True:
        resp = seller_product_list(
            last_id=last_id,
            limit=1000,
            visibility="ALL",
            client_id=seller_client_id,
            api_key=seller_api_key,
        )
        result = resp.get("result", {}) or {}
        items = result.get("items", []) or []
        if not items:
            break
        for item in items:
            product_id = item.get("product_id")
            if product_id is not None:
                product_ids.append(str(product_id))
        next_last_id = str(result.get("last_id", "") or "")
        if not next_last_id or next_last_id in seen_last_ids:
            break
        seen_last_ids.add(next_last_id)
        last_id = next_last_id

    rows: list[dict] = []
    chunk_size = 1000
    for offset in range(0, len(product_ids), chunk_size):
        batch = product_ids[offset : offset + chunk_size]
        info = seller_product_info_list(
            product_ids=batch,
            client_id=seller_client_id,
            api_key=seller_api_key,
        )
        items = info.get("items", []) or (info.get("result", {}) or {}).get("items", []) or []
        for item in items:
            sku = item.get("sku")
            if sku is None:
                continue
            rows.append(
                {
                    "sku": str(sku),
                    "product_id": str(item.get("id") or item.get("product_id") or ""),
                    "title": _normalize_text(item.get("name") or item.get("offer_id") or ""),
                    "offer_id": _normalize_text(item.get("offer_id") or ""),
                }
            )
    return tuple(rows)


def load_catalog(
    *,
    seller_client_id: str | None,
    seller_api_key: str | None,
) -> pd.DataFrame:
    df = pd.DataFrame(list(_load_catalog_cached(seller_client_id, seller_api_key)))
    if df.empty:
        return pd.DataFrame(columns=["sku", "product_id", "title", "offer_id"])
    return df.drop_duplicates(subset=["sku"]).copy()


@lru_cache(maxsize=64)
def _load_sales_history_cached(
    date_from: str,
    date_to: str,
    seller_client_id: str | None,
    seller_api_key: str | None,
) -> tuple[dict, ...]:
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
                    "day": str((dims[1] or {}).get("id", "")).strip() if len(dims) > 1 else "",
                    "revenue": float(metrics[0] or 0.0) if len(metrics) > 0 else 0.0,
                    "ordered_units": int(round(float(metrics[1] or 0.0))) if len(metrics) > 1 else 0,
                }
            )
        if len(data) < limit:
            break
        offset += limit
    return tuple(rows)


def load_sales_history(
    *,
    date_from: str,
    date_to: str,
    seller_client_id: str | None,
    seller_api_key: str | None,
) -> pd.DataFrame:
    df = pd.DataFrame(list(_load_sales_history_cached(date_from, date_to, seller_client_id, seller_api_key)))
    if df.empty:
        return pd.DataFrame(columns=["sku", "day", "revenue", "ordered_units"])
    df["day"] = pd.to_datetime(df["day"], errors="coerce")
    df = df.dropna(subset=["day"])
    df["sku"] = df["sku"].astype(str).str.strip()
    df = df[df["sku"].ne("")]
    return df


def _extract_query_row(raw: dict, sku: str) -> dict | None:
    query = raw.get("query") or raw.get("search_text") or raw.get("searchText") or raw.get("text")
    if not query and raw.get("dimensions"):
        query = (raw.get("dimensions") or [{}])[0].get("name")
    query = _normalize_text(query)
    if not query:
        return None

    searches = raw.get("searches")
    if searches is None:
        searches = raw.get("count")
    if searches is None and raw.get("metrics"):
        searches = raw.get("metrics", [0])[0]

    growth = raw.get("growth")
    if growth is None:
        current_period = float(raw.get("period_current", 0) or 0)
        previous_period = float(raw.get("period_previous", 0) or 0)
        if previous_period > 0:
            growth = (current_period - previous_period) / previous_period * 100.0
        elif current_period > 0:
            growth = 100.0
        else:
            growth = 0.0

    revenue = raw.get("revenue")
    return {
        "sku": str(sku),
        "query": query,
        "searches": float(searches or 0.0),
        "growth": float(growth or 0.0),
        "revenue": float(revenue or 0.0),
    }


@lru_cache(maxsize=64)
def _load_query_signals_cached(
    date_from: str,
    date_to: str,
    skus: tuple[str, ...],
    seller_client_id: str | None,
    seller_api_key: str | None,
) -> tuple[dict, ...]:
    if not ENABLE_QUERY_SIGNALS:
        return tuple()
    rows: list[dict] = []
    batch_size = 5
    for offset in range(0, len(skus), batch_size):
        batch = [str(s) for s in skus[offset : offset + batch_size] if str(s).strip()]
        if not batch:
            continue
        try:
            payload = seller_product_queries_details(
                date_from=date_from,
                date_to=date_to,
                skus=batch,
                limit_by_sku=5,
                page=0,
                page_size=100,
                sort_by="BY_SEARCHES",
                sort_dir="DESCENDING",
                client_id=seller_client_id,
                api_key=seller_api_key,
                timeout=12,
                max_retries=1,
            )
        except Exception:
            continue
        items = (
            payload.get("items", [])
            or (payload.get("result", {}) or {}).get("items", [])
            or (payload.get("result", {}) or {}).get("queries", [])
            or []
        )
        if not items:
            continue
        for item in items:
            raw_sku = item.get("sku") or item.get("product_sku") or item.get("item_id")
            sku = str(raw_sku or batch[0])
            row = _extract_query_row(item, sku)
            if row is not None:
                rows.append(row)
    return tuple(rows)


def load_query_signals(
    *,
    date_from: str,
    date_to: str,
    skus: tuple[str, ...],
    seller_client_id: str | None,
    seller_api_key: str | None,
) -> pd.DataFrame:
    df = pd.DataFrame(list(_load_query_signals_cached(date_from, date_to, skus, seller_client_id, seller_api_key)))
    if df.empty:
        return pd.DataFrame(columns=["sku", "query", "searches", "growth", "revenue"])
    return df


def build_date_span(date_from: date, date_to: date) -> int:
    return max(1, int((date_to - date_from).days) + 1)
