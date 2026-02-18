# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import logging
import os
from datetime import date, timedelta, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

from clients_seller import seller_finance_balance
from ui_helpers import load_company_configs, default_company_from_env


LOG_PATH = Path("app.log")
logger = logging.getLogger("ozon_ads")
if not logger.handlers:
    logger.setLevel(logging.INFO)
    handler = logging.FileHandler(LOG_PATH, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logger.addHandler(handler)


def _load_env_file(path: str = ".env") -> None:
    p = Path(path)
    if not p.exists():
        return
    for line in p.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        k, v = s.split("=", 1)
        k = k.strip()
        v = v.strip().strip("\"'")
        if k and k not in os.environ:
            os.environ[k] = v


def _ceil_int(value) -> int:
    try:
        return int((float(value) + 0.9999999))
    except Exception:
        return 0


def _fetch_balance_day(
    day_str: str,
    *,
    seller_client_id: str,
    seller_api_key: str,
):
    return seller_finance_balance(
        date_from=day_str,
        date_to=day_str,
        client_id=seller_client_id,
        api_key=seller_api_key,
    )


def _format_balance_row(day_str: str, data: dict) -> dict[str, str]:
    total = data.get("total", {}) or {}
    cashflows = data.get("cashflows", {}) or {}

    opening_balance = total.get("opening_balance", {}).get("value", 0)
    closing_balance = total.get("closing_balance", {}).get("value", 0)
    accrued = total.get("accrued", {}).get("value", 0)
    payments_list = total.get("payments", []) or []
    payments = sum(float(p.get("value", 0) or 0) for p in payments_list)

    sales = cashflows.get("sales", {}).get("amount", {}).get("value", 0)
    fee = cashflows.get("sales", {}).get("fee", {}).get("value", 0)

    services = cashflows.get("services", []) or []
    logistics = 0.0
    cross_docking = 0.0
    storage = 0.0
    marketing = 0.0
    promotion_with_cpo = 0.0
    acquiring = 0.0
    seller_bonuses = 0.0
    points_for_reviews = 0.0
    for s in services:
        name = str(s.get("name", "") or "")
        val = float(s.get("amount", {}).get("value", 0) or 0)
        if name in {"logistics", "courier_client_reinvoice"}:
            logistics += val
        if name == "cross_docking":
            cross_docking += val
        if name == "product_placement_in_ozon_warehouses":
            storage += val
        if name == "pay_per_click":
            marketing += val
        if name == "promotion_with_cost_per_order":
            promotion_with_cpo += val
        if name == "acquiring":
            acquiring += val
        if name == "seller_bonuses":
            seller_bonuses += val
        if name == "points_for_reviews":
            points_for_reviews += val

    sales_val = float(sales or 0)
    pct_logistics = (logistics / sales_val * 100.0) if sales_val else 0.0
    check_value = (
        sales
        + fee
        + acquiring
        + logistics
        + cross_docking
        + storage
        + marketing
        + promotion_with_cpo
        + points_for_reviews
        + seller_bonuses
        - accrued
    )

    return {
        "день": day_str,
        "на начало дня": str(_ceil_int(opening_balance)),
        "продажи": str(_ceil_int(sales)),
        "комиссия": str(_ceil_int(fee)),
        "эквайринг": str(_ceil_int(acquiring)),
        "выплаты": str(_ceil_int(payments)),
        "логистика": str(_ceil_int(logistics)),
        "кросс-докинг": str(_ceil_int(cross_docking)),
        "Хранение": str(_ceil_int(storage)),
        "реклама": str(_ceil_int(marketing)),
        "реклама - за заказ": str(_ceil_int(promotion_with_cpo)),
        "баллы за отзывы": str(_ceil_int(points_for_reviews)),
        "бонусы продавца": str(_ceil_int(seller_bonuses)),
        "на конец дня": str(_ceil_int(closing_balance)),
        "изменение": str(_ceil_int(accrued)),
        "проверка": str(_ceil_int(check_value)),
        "% логистики": f"{pct_logistics:.1f}",
    }


def _send_telegram_message(token: str, chat_id: str, text: str) -> None:
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
    }
    r = requests.post(url, json=payload, timeout=30)
    r.raise_for_status()


def main() -> int:
    _load_env_file(".env")

    tz_name = os.getenv("TZ", "Europe/Moscow")
    tz = ZoneInfo(tz_name)
    now = datetime.now(tz)
    yesterday = (now.date() - timedelta(days=1)).isoformat()

    company_name = os.getenv("COMPANY_NAME")
    company_configs = load_company_configs(".env")
    if company_name and company_name in company_configs:
        creds = company_configs[company_name]
    else:
        creds = default_company_from_env()

    seller_client_id = (creds.get("seller_client_id") or "").strip()
    seller_api_key = (creds.get("seller_api_key") or "").strip()
    if not seller_client_id or not seller_api_key:
        logger.error("Missing seller creds")
        return 2

    token = os.getenv("TG_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TG_CHAT_ID", "").strip()
    if not token or not chat_id:
        logger.error("Missing TG_BOT_TOKEN or TG_CHAT_ID")
        return 3

    data = _fetch_balance_day(
        yesterday,
        seller_client_id=seller_client_id,
        seller_api_key=seller_api_key,
    )
    row = _format_balance_row(yesterday, data)

    ordered_keys = [
        "день",
        "на начало дня",
        "на конец дня",
        "изменение",
        "продажи",
        "комиссия",
        "эквайринг",
        "выплаты",
        "логистика",
        "кросс-докинг",
        "Хранение",
        "реклама",
        "реклама - за заказ",
        "баллы за отзывы",
        "бонусы продавца",
        "проверка",
        "% логистики",
    ]
    lines = [f"{k}: {row.get(k, '')}" for k in ordered_keys]
    text = "\n".join(lines)
    _send_telegram_message(token, chat_id, text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
