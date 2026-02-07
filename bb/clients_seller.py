import os
import time
import requests

SELLER_BASE = "https://api-seller.ozon.ru"


def must_env(name: str) -> str:
    v = os.getenv(name)
    if not v:
        raise RuntimeError(f"Не задано в .env: {name}")
    return v


def parse_money(x) -> float:
    if x is None:
        return 0.0
    if isinstance(x, (int, float)):
        return float(x)
    s = str(x).strip().replace(" ", "").replace(",", ".")
    try:
        return float(s)
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
    """
    Seller API часто отвечает 429. Для /v1/analytics/data по доке есть лимиты.
    Делаем backoff (учитываем Retry-After если он есть).
    """
    backoff = 2.0
    last_exc = None

    for _attempt in range(max_retries):
        try:
            r = requests.post(url, json=body, headers=headers, timeout=timeout)

            if r.status_code == 429:
                ra = r.headers.get("Retry-After")
                if ra:
                    try:
                        sleep_s = float(ra)
                    except Exception:
                        sleep_s = backoff
                else:
                    sleep_s = max(backoff, 10.0)

                time.sleep(sleep_s)
                backoff = min(backoff * 2, 70.0)
                continue

            if 500 <= r.status_code < 600:
                time.sleep(backoff)
                backoff = min(backoff * 2, 70.0)
                continue

            r.raise_for_status()
            return r

        except requests.RequestException as e:
            last_exc = e
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
    """
    POST /v1/analytics/data

    dimension=["sku","day"], metrics=["revenue","ordered_units"]

    Возвращаем:
      - by_sku: dict sku -> (revenue_sum, units_sum) за период
      - by_day: dict day -> (revenue_sum, units_sum) за период
      - by_day_sku: dict (day, sku) -> (revenue, units)
    """
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

        r = _post_with_backoff(url, headers=headers, body=body, timeout=60)
        j = r.json()
        data = j.get("result", {}).get("data", []) or []

        if not data:
            break

        for row in data:
            dims = row.get("dimensions", []) or []
            mets = row.get("metrics", []) or []

            # dimensions: ["sku","day"] -> [0]=sku, [1]=day
            sku = str(dims[0].get("id")) if len(dims) > 0 else ""
            day = str(dims[1].get("id")) if len(dims) > 1 else ""

            revenue = parse_money(mets[0]) if len(mets) > 0 else 0.0
            units_raw = mets[1] if len(mets) > 1 else 0
            try:
                units = int(units_raw) if units_raw is not None else 0
            except Exception:
                units = 0

            if not sku or not day:
                continue

            # (day, sku)
            prev = by_day_sku.get((day, sku))
            if prev is None:
                by_day_sku[(day, sku)] = (revenue, units)
            else:
                by_day_sku[(day, sku)] = (prev[0] + revenue, prev[1] + units)

            # sku totals
            prev_s = by_sku.get(sku)
            if prev_s is None:
                by_sku[sku] = (revenue, units)
            else:
                by_sku[sku] = (prev_s[0] + revenue, prev_s[1] + units)

            # day totals
            prev_d = by_day.get(day)
            if prev_d is None:
                by_day[day] = (revenue, units)
            else:
                by_day[day] = (prev_d[0] + revenue, prev_d[1] + units)

        if len(data) < limit:
            break

        offset += limit

    return by_sku, by_day, by_day_sku


def seller_total_sales_all(date_from: str, date_to: str, limit: int = 1000):
    """
    Backward-compatible wrapper.
    Старый код ожидал sku -> (revenue, units) за период.
    """
    by_sku, _by_day, _by_day_sku = seller_analytics_sku_day(date_from, date_to, limit=limit)
    return by_sku


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
):
    """
    POST /v1/analytics/product-queries/details
    """
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
        "skus": [str(s) for s in skus],
        "sort_by": sort_by,
        "sort_dir": sort_dir,
    }
    r = _post_with_backoff(url, headers=headers, body=body, timeout=60)
    return r.json()


def seller_product_info_prices(
    *,
    offer_ids: list[str] | None = None,
    product_ids: list[str] | None = None,
    visibility: str = "ALL",
    cursor: str = "",
    limit: int = 100,
    client_id: str | None = None,
    api_key: str | None = None,
):
    """
    POST /v5/product/info/prices
    """
    url = f"{SELLER_BASE}/v5/product/info/prices"
    headers = {
        "Client-Id": client_id or must_env("SELLER_CLIENT_ID"),
        "Api-Key": api_key or must_env("SELLER_API_KEY"),
    }
    body = {
        "cursor": cursor,
        "filter": {
            "offer_id": [str(x) for x in (offer_ids or [])],
            "product_id": [str(x) for x in (product_ids or [])],
            "visibility": visibility,
        },
        "limit": int(limit),
    }
    r = _post_with_backoff(url, headers=headers, body=body, timeout=60)
    return r.json()


def seller_finance_balance(
    *,
    date_from: str,
    date_to: str,
    client_id: str | None = None,
    api_key: str | None = None,
):
    """
    POST /v1/finance/balance
    """
    url = f"{SELLER_BASE}/v1/finance/balance"
    headers = {
        "Client-Id": client_id or must_env("SELLER_CLIENT_ID"),
        "Api-Key": api_key or must_env("SELLER_API_KEY"),
    }
    body = {
        "date_from": date_from,
        "date_to": date_to,
    }
    r = _post_with_backoff(url, headers=headers, body=body, timeout=60)
    return r.json()


def seller_product_list(
    *,
    last_id: str = "",
    limit: int = 1000,
    visibility: str = "ALL",
    client_id: str | None = None,
    api_key: str | None = None,
):
    """
    POST /v3/product/list
    """
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
    r = _post_with_backoff(url, headers=headers, body=body, timeout=60)
    return r.json()


def seller_product_info_list(
    *,
    product_ids: list[str],
    client_id: str | None = None,
    api_key: str | None = None,
):
    """
    POST /v3/product/info/list
    """
    url = f"{SELLER_BASE}/v3/product/info/list"
    headers = {
        "Client-Id": client_id or must_env("SELLER_CLIENT_ID"),
        "Api-Key": api_key or must_env("SELLER_API_KEY"),
    }
    body = {"product_id": [int(pid) for pid in product_ids if str(pid).isdigit()]}
    r = _post_with_backoff(url, headers=headers, body=body, timeout=60)
    return r.json()


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
    """
    POST /v1/analytics/stocks
    """
    url = f"{SELLER_BASE}/v1/analytics/stocks"
    headers = {
        "Client-Id": client_id or must_env("SELLER_CLIENT_ID"),
        "Api-Key": api_key or must_env("SELLER_API_KEY"),
    }
    body = {
        "skus": [int(s) for s in skus if str(s).isdigit()],
    }
    if cluster_ids:
        body["cluster_ids"] = [int(c) for c in cluster_ids]
    if warehouse_ids:
        body["warehouse_ids"] = [str(w) for w in warehouse_ids]
    if turnover_grades:
        body["turnover_grades"] = turnover_grades
    if item_tags:
        body["item_tags"] = item_tags
    r = _post_with_backoff(url, headers=headers, body=body, timeout=60)
    return r.json()
