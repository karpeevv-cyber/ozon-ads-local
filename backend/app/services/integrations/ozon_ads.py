import os
import time

import requests

PERF_BASE = "https://api-performance.ozon.ru"
_SESSION = requests.Session()
_TOKEN_CACHE: dict[tuple[str, str], tuple[str, float]] = {}
_TOKEN_TTL_SECONDS = 25 * 60
_RETRY_STATUS = {429, 500, 502, 503, 504}
_MAX_RETRIES = 3
_RETRY_BASE_DELAY = 0.8


def must_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def _request_with_retry(method: str, url: str, **kwargs) -> requests.Response:
    last_error: Exception | None = None
    for attempt in range(_MAX_RETRIES):
        try:
            response = _SESSION.request(method, url, **kwargs)
            if response.status_code in _RETRY_STATUS and attempt < (_MAX_RETRIES - 1):
                retry_after = response.headers.get("Retry-After")
                if retry_after:
                    try:
                        delay = float(retry_after)
                    except ValueError:
                        delay = _RETRY_BASE_DELAY * (2**attempt)
                else:
                    delay = _RETRY_BASE_DELAY * (2**attempt)
                time.sleep(max(0.2, delay))
                continue
            return response
        except requests.RequestException as exc:
            last_error = exc
            if attempt >= (_MAX_RETRIES - 1):
                raise
            time.sleep(_RETRY_BASE_DELAY * (2**attempt))

    if last_error:
        raise last_error
    raise RuntimeError("Failed to execute request")


def perf_token(client_id: str | None = None, client_secret: str | None = None) -> str:
    url = f"{PERF_BASE}/api/client/token"
    resolved_id = client_id or must_env("PERF_CLIENT_ID")
    resolved_secret = client_secret or must_env("PERF_CLIENT_SECRET")
    cache_key = (resolved_id, resolved_secret)
    cached = _TOKEN_CACHE.get(cache_key)
    if cached:
        token, ts = cached
        if (time.time() - ts) < _TOKEN_TTL_SECONDS:
            return token

    data = {
        "client_id": resolved_id,
        "client_secret": resolved_secret,
        "grant_type": "client_credentials",
    }
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    response = _request_with_retry("POST", url, data=data, headers=headers, timeout=30)
    response.raise_for_status()
    token = response.json()["access_token"]
    _TOKEN_CACHE[cache_key] = (token, time.time())
    return token


def get_campaigns(token: str) -> list[dict]:
    url = f"{PERF_BASE}/api/client/campaign"
    response = _request_with_retry(
        "GET",
        url,
        params={"advObjectType": "SKU"},
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
        timeout=30,
    )
    response.raise_for_status()
    return response.json().get("list", [])


def get_running_campaigns(*, client_id: str | None = None, client_secret: str | None = None) -> list[dict]:
    token = perf_token(client_id=client_id, client_secret=client_secret)
    campaigns = get_campaigns(token)
    running = [campaign for campaign in campaigns if campaign.get("state") == "CAMPAIGN_STATE_RUNNING"]
    running.sort(key=lambda item: (item.get("title") or "").lower())
    return running


def get_campaign_products_page(token: str, campaign_id: str, page: int = 1, page_size: int = 100) -> dict:
    url = f"{PERF_BASE}/api/client/campaign/{campaign_id}/v2/products"
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    params = {"page": page, "pageSize": page_size}
    response = _request_with_retry("GET", url, headers=headers, params=params, timeout=30)
    response.raise_for_status()
    return response.json()


def get_campaign_products_all(token: str, campaign_id: str, page_size: int = 100) -> list[dict]:
    items: list[dict] = []
    page = 1
    while True:
        payload = get_campaign_products_page(token, campaign_id, page=page, page_size=page_size)
        page_items = payload.get("products") or payload.get("list") or payload.get("items") or []
        if not page_items:
            break
        items.extend(page_items)
        if len(page_items) < page_size:
            break
        page += 1
    return items


def get_campaign_stats_json(token: str, date_from: str, date_to: str, campaign_ids: list[str]) -> dict:
    url = f"{PERF_BASE}/api/client/statistics/campaign/product/json"
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    params = [("dateFrom", date_from), ("dateTo", date_to)]
    params += [("campaignIds", str(campaign_id)) for campaign_id in campaign_ids]
    response = _request_with_retry("GET", url, headers=headers, params=params, timeout=60)
    response.raise_for_status()
    return response.json()


def update_campaign_product_bids(token: str, campaign_id: str, bids: list[dict]) -> dict:
    url = f"{PERF_BASE}/api/client/campaign/{campaign_id}/products"
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    response = _request_with_retry("PUT", url, json={"bids": bids}, headers=headers, timeout=30)
    response.raise_for_status()
    try:
        return response.json()
    except Exception:
        return {"status_code": response.status_code, "text": response.text}
