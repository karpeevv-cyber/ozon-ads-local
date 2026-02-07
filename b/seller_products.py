import os
import time
import requests
from dotenv import load_dotenv

load_dotenv()

SELLER_BASE = "https://api-seller.ozon.ru"


def must_env(name: str) -> str:
    v = os.getenv(name)
    if not v:
        raise RuntimeError(f"Не задано в .env: {name}")
    return v


def seller_headers() -> dict:
    return {
        "Client-Id": must_env("SELLER_CLIENT_ID"),
        "Api-Key": must_env("SELLER_API_KEY"),
    }


def _post_json(url: str, body: dict, timeout: int = 60) -> dict:
    r = requests.post(url, json=body, headers=seller_headers(), timeout=timeout)
    # лёгкий backoff на 429 (на случай лимитов)
    if r.status_code == 429:
        time.sleep(2.0)
        r = requests.post(url, json=body, headers=seller_headers(), timeout=timeout)
    r.raise_for_status()
    return r.json()


def seller_product_list(limit: int = 1000) -> list[dict]:
    """
    POST /v3/product/list
    Возвращаем справочник товаров (offer_id <-> product_id) + флаги из ответа.
    """
    url = f"{SELLER_BASE}/v3/product/list"
    last_id = ""
    out: list[dict] = []

    while True:
        body = {
            "filter": {},
            "last_id": last_id,
            "limit": int(limit),
        }
        j = _post_json(url, body)
        result = j.get("result", {}) or {}
        items = result.get("items", []) or []
        if not items:
            break

        for it in items:
            out.append(
                {
                    "offer_id": it.get("offer_id"),
                    "product_id": it.get("product_id"),
                    "archived": it.get("archived"),
                    "has_fbo_stocks": it.get("has_fbo_stocks"),
                    "has_fbs_stocks": it.get("has_fbs_stocks"),
                    "is_discounted": it.get("is_discounted"),
                }
            )

        new_last_id = result.get("last_id") or ""
        if not new_last_id or new_last_id == last_id:
            break
        last_id = new_last_id

    return out


def seller_product_info_prices(
    product_ids: list[int] | None = None,
    offer_ids: list[str] | None = None,
    visibility: str = "ALL",
    limit: int = 100,
    cursor: str = "",
) -> dict:
    """
    POST /v5/product/info/prices
    В body есть cursor, filter:{offer_id/product_id/visibility}, limit.
    Возвращаем raw json.
    """
    if not product_ids and not offer_ids:
        raise ValueError("Нужно передать product_ids или offer_ids")

    url = f"{SELLER_BASE}/v5/product/info/prices"
    flt: dict = {"visibility": visibility}

    if offer_ids:
        flt["offer_id"] = [str(x) for x in offer_ids]
    if product_ids:
        flt["product_id"] = [int(x) for x in product_ids]

    body = {
        "cursor": cursor,
        "filter": flt,
        "limit": int(limit),
    }
    return _post_json(url, body)

def report_products_create(
    language: str = "DEFAULT",
    offer_ids: list[str] | None = None,
    ozon_skus: list[int] | None = None,
    search: str = "",
    visibility: str = "ALL",
) -> str:
    """
    POST /v1/report/products/create

    Поля строго по скрину из доки: language, offer_id, search, sku, visibility.
    Возвращает report_code = result.code
    """
    if not (offer_ids or ozon_skus or search):
        # не запрещено докой, но защитимся от случайного "все товары без фильтра"
        raise ValueError("Нужно задать хотя бы один фильтр: offer_ids или ozon_skus или search")

    url = f"{SELLER_BASE}/v1/report/products/create"

    body: dict = {
        "language": language,
        "visibility": visibility,
    }
    if offer_ids:
        body["offer_id"] = [str(x) for x in offer_ids]
    if ozon_skus:
        body["sku"] = [int(x) for x in ozon_skus]
    if search:
        body["search"] = str(search)

    j = _post_json(url, body)
    result = j.get("result", {}) or {}
    code = result.get("code")
    if not code:
        raise RuntimeError(f"Не найден result.code в ответе: {j}")
    return str(code)

import io

import pandas as pd
import requests


def _download_file_bytes(url: str, timeout: int = 120) -> bytes:
    if not url:
        raise ValueError("url пустой")
    r = requests.get(url, timeout=timeout)
    r.raise_for_status()
    return r.content

def report_info(code: str) -> dict:
    """
    POST /v1/report/info

    В body: {"code": "<REPORT_...>"}
    Возвращает raw json, в result обычно есть:
    - status: waiting | processing | success | failed
    - file: ссылка на файл (если success)
    - error, created_at, expires_at, report_type, params ...
    """
    if not code or not str(code).strip():
        raise ValueError("code обязателен")

    url = f"{SELLER_BASE}/v1/report/info"
    body = {"code": str(code).strip()}
    return _post_json(url, body)


def _read_report_to_df(file_url: str) -> pd.DataFrame:
    """
    Скачивает report file по URL и парсит в DataFrame.
    Поддержка: CSV / XLSX.
    CSV: пытаемся ; потом , (у Озона часто ;)
    """
    data = _download_file_bytes(file_url)

    url_l = file_url.lower()
    if url_l.endswith(".xlsx") or url_l.endswith(".xls"):
        return pd.read_excel(io.BytesIO(data))

    # иначе считаем CSV (или неизвестное, но чаще CSV)
    bio = io.BytesIO(data)

    # попытка №1: частый для RU csv — ';' и UTF-8-SIG
    try:
        return pd.read_csv(bio, sep=";", encoding="utf-8-sig")
    except Exception:
        pass

    # попытка №2: запятая
    bio = io.BytesIO(data)
    return pd.read_csv(bio, sep=",", encoding="utf-8-sig")
