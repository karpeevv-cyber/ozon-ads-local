from __future__ import annotations

import os
import time

import requests

SELLER_BASE = "https://api-seller.ozon.ru"
_SESSION = requests.Session()


def must_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def parse_money(value) -> float:
    if value is None:
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    raw = str(value).strip().replace(" ", "").replace(",", ".")
    try:
        return float(raw)
    except ValueError:
        return 0.0


def _post_with_backoff(
    url: str,
    *,
    headers: dict,
    body: dict,
    timeout: int = 60,
    max_retries: int = 6,
):
    backoff = 2.0
    last_exc = None

    for _attempt in range(max_retries):
        try:
            response = _SESSION.post(url, json=body, headers=headers, timeout=timeout)

            if response.status_code == 429:
                retry_after = response.headers.get("Retry-After")
                if retry_after:
                    try:
                        sleep_s = float(retry_after)
                    except Exception:
                        sleep_s = backoff
                else:
                    sleep_s = max(backoff, 10.0)

                time.sleep(sleep_s)
                backoff = min(backoff * 2, 70.0)
                continue

            if 500 <= response.status_code < 600:
                time.sleep(backoff)
                backoff = min(backoff * 2, 70.0)
                continue

            response.raise_for_status()
            return response
        except requests.HTTPError:
            raise
        except requests.RequestException as exc:
            last_exc = exc
            time.sleep(backoff)
            backoff = min(backoff * 2, 70.0)

    if last_exc:
        raise last_exc
    raise RuntimeError("Seller request failed without exception")


def seller_analytics_sku_day(
    date_from: str,
    date_to: str,
    limit: int = 1000,
    *,
    client_id: str | None = None,
    api_key: str | None = None,
):
    url = f"{SELLER_BASE}/v1/analytics/data"
    headers = {
        "Client-Id": client_id or must_env("SELLER_CLIENT_ID"),
        "Api-Key": api_key or must_env("SELLER_API_KEY"),
    }

    offset = 0
    by_sku: dict[str, tuple[float, int]] = {}
    by_day: dict[str, tuple[float, int]] = {}
    by_day_sku: dict[tuple[str, str], tuple[float, int]] = {}

    while True:
        body = {
            "date_from": date_from,
            "date_to": date_to,
            "dimension": ["sku", "day"],
            "metrics": ["revenue", "ordered_units"],
            "limit": int(limit),
            "offset": int(offset),
        }

        response = _post_with_backoff(url, headers=headers, body=body, timeout=60)
        data = response.json().get("result", {}).get("data", []) or []

        if not data:
            break

        for row in data:
            dims = row.get("dimensions", []) or []
            metrics = row.get("metrics", []) or []

            sku = str(dims[0].get("id")) if len(dims) > 0 else ""
            day = str(dims[1].get("id")) if len(dims) > 1 else ""
            revenue = parse_money(metrics[0]) if len(metrics) > 0 else 0.0
            units_raw = metrics[1] if len(metrics) > 1 else 0
            try:
                units = int(units_raw) if units_raw is not None else 0
            except Exception:
                units = 0

            if not sku or not day:
                continue

            prev_day_sku = by_day_sku.get((day, sku))
            if prev_day_sku is None:
                by_day_sku[(day, sku)] = (revenue, units)
            else:
                by_day_sku[(day, sku)] = (prev_day_sku[0] + revenue, prev_day_sku[1] + units)

            prev_sku = by_sku.get(sku)
            if prev_sku is None:
                by_sku[sku] = (revenue, units)
            else:
                by_sku[sku] = (prev_sku[0] + revenue, prev_sku[1] + units)

            prev_day = by_day.get(day)
            if prev_day is None:
                by_day[day] = (revenue, units)
            else:
                by_day[day] = (prev_day[0] + revenue, prev_day[1] + units)

        if len(data) < limit:
            break
        offset += limit

    return by_sku, by_day, by_day_sku


def seller_total_sales_all(date_from: str, date_to: str, limit: int = 1000):
    by_sku, _by_day, _by_day_sku = seller_analytics_sku_day(date_from, date_to, limit=limit)
    return by_sku


def seller_analytics_data(
    *,
    date_from: str,
    date_to: str,
    dimension: list[str],
    metrics: list[str],
    limit: int = 1000,
    offset: int = 0,
    filters: list[dict] | None = None,
    sort: list[dict] | None = None,
    client_id: str | None = None,
    api_key: str | None = None,
):
    url = f"{SELLER_BASE}/v1/analytics/data"
    headers = {
        "Client-Id": client_id or must_env("SELLER_CLIENT_ID"),
        "Api-Key": api_key or must_env("SELLER_API_KEY"),
    }
    body = {
        "date_from": date_from,
        "date_to": date_to,
        "dimension": list(dimension or []),
        "metrics": list(metrics or []),
        "limit": int(limit),
        "offset": int(offset),
    }
    if filters:
        body["filters"] = filters
    if sort:
        body["sort"] = sort
    response = _post_with_backoff(url, headers=headers, body=body, timeout=60)
    return response.json()


def seller_product_queries_details(
    *,
    date_from: str,
    date_to: str,
    skus: list[str],
    limit_by_sku: int = 0,
    page: int = 0,
    page_size: int = 1000,
    sort_by: str = "BY_SEARCHES",
    sort_dir: str = "DESCENDING",
    client_id: str | None = None,
    api_key: str | None = None,
    timeout: int = 20,
    max_retries: int = 2,
):
    url = f"{SELLER_BASE}/v1/analytics/product-queries/details"
    headers = {
        "Client-Id": client_id or must_env("SELLER_CLIENT_ID"),
        "Api-Key": api_key or must_env("SELLER_API_KEY"),
    }
    body = {
        "date_from": date_from,
        "date_to": date_to,
        "limit_by_sku": int(limit_by_sku),
        "page": int(page),
        "page_size": int(page_size),
        "skus": [str(sku) for sku in skus],
        "sort_by": sort_by,
        "sort_dir": sort_dir,
    }
    response = _post_with_backoff(
        url,
        headers=headers,
        body=body,
        timeout=int(timeout),
        max_retries=int(max_retries),
    )
    return response.json()


def seller_finance_balance(
    *,
    date_from: str,
    date_to: str,
    client_id: str | None = None,
    api_key: str | None = None,
):
    url = f"{SELLER_BASE}/v1/finance/balance"
    headers = {
        "Client-Id": client_id or must_env("SELLER_CLIENT_ID"),
        "Api-Key": api_key or must_env("SELLER_API_KEY"),
    }
    body = {
        "date_from": date_from,
        "date_to": date_to,
    }
    response = _post_with_backoff(url, headers=headers, body=body, timeout=60)
    return response.json()


def seller_product_list(
    *,
    last_id: str = "",
    limit: int = 1000,
    visibility: str = "ALL",
    client_id: str | None = None,
    api_key: str | None = None,
):
    url = f"{SELLER_BASE}/v3/product/list"
    headers = {
        "Client-Id": client_id or must_env("SELLER_CLIENT_ID"),
        "Api-Key": api_key or must_env("SELLER_API_KEY"),
    }
    body = {
        "last_id": str(last_id),
        "limit": int(limit),
        "filter": {"visibility": visibility},
    }
    response = _post_with_backoff(url, headers=headers, body=body, timeout=60)
    return response.json()


def seller_product_info_list(
    *,
    product_ids: list[str],
    client_id: str | None = None,
    api_key: str | None = None,
):
    url = f"{SELLER_BASE}/v3/product/info/list"
    headers = {
        "Client-Id": client_id or must_env("SELLER_CLIENT_ID"),
        "Api-Key": api_key or must_env("SELLER_API_KEY"),
    }
    body = {"product_id": [int(pid) for pid in product_ids if str(pid).isdigit()]}
    response = _post_with_backoff(url, headers=headers, body=body, timeout=60)
    return response.json()


def seller_product_info_stocks(
    *,
    offer_ids: list[str],
    client_id: str | None = None,
    api_key: str | None = None,
):
    url = f"{SELLER_BASE}/v4/product/info/stocks"
    headers = {
        "Client-Id": client_id or must_env("SELLER_CLIENT_ID"),
        "Api-Key": api_key or must_env("SELLER_API_KEY"),
    }
    body = {
        "filter": {
            "offer_id": [str(value) for value in offer_ids if str(value).strip()],
            "visibility": "ALL",
        },
        "limit": 1000,
    }
    response = _post_with_backoff(url, headers=headers, body=body, timeout=60)
    return response.json()


def seller_analytics_stocks(
    *,
    skus: list[str],
    cluster_ids: list[int] | None = None,
    warehouse_ids: list[str] | None = None,
    turnover_grades: list[str] | None = None,
    item_tags: list[str] | None = None,
    client_id: str | None = None,
    api_key: str | None = None,
):
    url = f"{SELLER_BASE}/v1/analytics/stocks"
    headers = {
        "Client-Id": client_id or must_env("SELLER_CLIENT_ID"),
        "Api-Key": api_key or must_env("SELLER_API_KEY"),
    }
    body = {"skus": [int(sku) for sku in skus if str(sku).isdigit()]}
    if cluster_ids:
        body["cluster_ids"] = [int(cluster_id) for cluster_id in cluster_ids]
    if warehouse_ids:
        body["warehouse_ids"] = [str(warehouse_id) for warehouse_id in warehouse_ids]
    if turnover_grades:
        body["turnover_grades"] = turnover_grades
    if item_tags:
        body["item_tags"] = item_tags
    response = _post_with_backoff(url, headers=headers, body=body, timeout=60)
    return response.json()


def seller_supply_order_list(
    *,
    filter: dict,
    last_id: str = "",
    limit: int = 100,
    sort_by: str = "ORDER_CREATION",
    sort_dir: str = "DESC",
    client_id: str | None = None,
    api_key: str | None = None,
):
    url = f"{SELLER_BASE}/v3/supply-order/list"
    headers = {
        "Client-Id": client_id or must_env("SELLER_CLIENT_ID"),
        "Api-Key": api_key or must_env("SELLER_API_KEY"),
    }
    body = {
        "filter": filter or {},
        "last_id": str(last_id or ""),
        "limit": int(limit),
        "sort_by": str(sort_by),
        "sort_dir": str(sort_dir),
    }
    response = _post_with_backoff(url, headers=headers, body=body, timeout=60)
    return response.json()


def seller_supply_order_get(
    *,
    order_ids: list[str],
    client_id: str | None = None,
    api_key: str | None = None,
):
    url = f"{SELLER_BASE}/v3/supply-order/get"
    headers = {
        "Client-Id": client_id or must_env("SELLER_CLIENT_ID"),
        "Api-Key": api_key or must_env("SELLER_API_KEY"),
    }
    ids = [str(value) for value in order_ids if str(value).strip()]
    body_variants = [
        {"order_ids": ids},
        {"supply_order_ids": ids},
        {"ids": ids},
    ]
    last_exc = None
    for body in body_variants:
        try:
            response = _post_with_backoff(url, headers=headers, body=body, timeout=60)
            return response.json()
        except Exception as exc:
            last_exc = exc
    if last_exc:
        raise last_exc
    raise RuntimeError("seller_supply_order_get failed without exception")


def seller_supply_order_bundle_query(
    *,
    bundle_ids: list[str],
    dropoff_warehouse_id: str,
    storage_warehouse_ids: list[str],
    limit: int = 100,
    sort_field: str = "NAME",
    is_asc: bool = True,
    last_id: str = "",
    client_id: str | None = None,
    api_key: str | None = None,
):
    url = f"{SELLER_BASE}/v1/supply-order/bundle"
    headers = {
        "Client-Id": client_id or must_env("SELLER_CLIENT_ID"),
        "Api-Key": api_key or must_env("SELLER_API_KEY"),
    }
    body = {
        "bundle_ids": [str(value) for value in bundle_ids if str(value).strip()],
        "is_asc": bool(is_asc),
        "limit": int(limit),
        "sort_field": str(sort_field),
    }
    storage_ids = [str(value) for value in storage_warehouse_ids if str(value).strip()]
    if str(dropoff_warehouse_id or "").strip() and storage_ids:
        body["item_tags_calculation"] = {
            "dropoff_warehouse_id": str(dropoff_warehouse_id),
            "storage_warehouse_ids": storage_ids,
        }
    if str(last_id or "").strip():
        body["last_id"] = str(last_id)
    response = _post_with_backoff(url, headers=headers, body=body, timeout=60)
    return response.json()
