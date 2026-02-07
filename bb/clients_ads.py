import os
import requests

PERF_BASE = "https://api-performance.ozon.ru"


def must_env(name: str) -> str:
    v = os.getenv(name)
    if not v:
        raise RuntimeError(f"Не задано в .env: {name}")
    return v


def perf_token(client_id: str | None = None, client_secret: str | None = None) -> str:
    url = f"{PERF_BASE}/api/client/token"
    data = {
        "client_id": client_id or must_env("PERF_CLIENT_ID"),
        "client_secret": client_secret or must_env("PERF_CLIENT_SECRET"),
        "grant_type": "client_credentials",
    }
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    r = requests.post(url, data=data, headers=headers, timeout=30)
    r.raise_for_status()
    return r.json()["access_token"]


def get_campaigns(token: str):
    url = f"{PERF_BASE}/api/client/campaign"
    r = requests.get(
        url,
        params={"advObjectType": "SKU"},
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
        timeout=30,
    )
    r.raise_for_status()
    return r.json().get("list", [])


def get_campaign_products_page(token: str, campaign_id: str, page: int = 1, page_size: int = 100):
    url = f"{PERF_BASE}/api/client/campaign/{campaign_id}/v2/products"
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    params = {"page": page, "pageSize": page_size}
    r = requests.get(url, headers=headers, params=params, timeout=30)
    r.raise_for_status()
    return r.json()


def get_campaign_products_all(token: str, campaign_id: str, page_size: int = 100):
    all_items = []
    page = 1
    while True:
        resp = get_campaign_products_page(token, campaign_id, page=page, page_size=page_size)
        items = resp.get("products") or resp.get("list") or resp.get("items") or []
        if not items:
            break
        all_items.extend(items)
        if len(items) < page_size:
            break
        page += 1
    return all_items


def get_campaign_stats_json(token: str, date_from: str, date_to: str, campaign_ids: list[str]):
    """
    Статистика по кампаниям (JSON):
    GET /api/client/statistics/campaign/product/json

    Формат батча: campaignIds повторяется в query несколько раз:
    ...?dateFrom=...&dateTo=...&campaignIds=1&campaignIds=2
    """
    url = f"{PERF_BASE}/api/client/statistics/campaign/product/json"
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}

    params = [("dateFrom", date_from), ("dateTo", date_to)]
    params += [("campaignIds", str(cid)) for cid in campaign_ids]

    r = requests.get(url, headers=headers, params=params, timeout=60)
    r.raise_for_status()
    return r.json()

def update_campaign_product_bids(token: str, campaign_id: str, bids: list[dict]):
    """
    PUT /api/client/campaign/{campaignId}/products
    body: {"bids":[{"sku":"...","bid":"..."}]}
    ВАЖНО: bid отправляй в тех же единицах, что и current_bid из get_campaign_products_all().
    """
    url = f"{PERF_BASE}/api/client/campaign/{campaign_id}/products"
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    payload = {"bids": bids}

    r = requests.put(url, json=payload, headers=headers, timeout=30)
    r.raise_for_status()
    # по доке может вернуть null/пусто — тогда просто вернём status_code
    try:
        return r.json()
    except Exception:
        return {"status_code": r.status_code, "text": r.text}
