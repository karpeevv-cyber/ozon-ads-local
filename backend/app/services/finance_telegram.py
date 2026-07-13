from __future__ import annotations

import asyncio
import logging
import os
import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import requests

from app.services.company_config import default_company_from_env, load_runtime_company_configs
from app.services.finance_summary import get_finance_summary

logger = logging.getLogger("uvicorn.error")


FinanceRow = dict[str, int | float | str]


FINANCE_TELEGRAM_COLUMNS: list[tuple[str, tuple[str, ...]]] = [
    ("день", ("day",)),
    ("продажи", ("revenue",)),
    ("дрр", ("drr",)),
    ("на начало дня", ("opening_balance",)),
    ("на конец дня", ("closing_balance",)),
    ("изменение", ("change",)),
    ("возможно избежать", ("avoidable",)),
    ("комиссия + эквайринг", ("fee", "acquiring")),
    ("выплаты", ("payments",)),
    ("комиссия за выплату", ("payment_commission",)),
    ("логистика", ("logistics",)),
    ("обратная логистика + возвраты", ("reverse_logistics", "returns")),
    ("кросс-докинг + приемка", ("cross_docking", "acceptance")),
    ("вывоз со склада", ("export",)),
    ("хранение товаров в ПВЗ", ("pickup_point_storage",)),
    ("ошибки", ("errors",)),
    ("обработка брака", ("defects",)),
    ("взаимозачет", ("mutual_offset",)),
    ("декомпенсация", ("decompensation",)),
    ("утилизация", ("disposal",)),
    ("Хранение", ("storage",)),
    ("реклама", ("marketing",)),
    ("реклама - за заказ", ("promotion_with_cpo",)),
    ("баллы за отзывы", ("points_for_reviews",)),
    ("бонусы продавца", ("seller_bonuses",)),
    ("проверка", ("check",)),
    ("% логистики", ("logistics_pct",)),
]


def _number(value: object) -> float:
    try:
        return float(value or 0)
    except Exception:
        return 0.0


def _format_value(value: object, *, is_percent: bool = False) -> str:
    if is_percent:
        return f"{_number(value):.1f}%"
    if isinstance(value, str):
        return value
    num = _number(value)
    return str(int(num)) if num.is_integer() else f"{num:.2f}".rstrip("0").rstrip(".")


def _column_value(row: FinanceRow, keys: tuple[str, ...]) -> object:
    if keys == ("drr",):
        sales = _number(row.get("revenue", 0))
        ads = _number(row.get("marketing", 0)) + _number(row.get("promotion_with_cpo", 0))
        return (-ads / sales * 100.0) if sales else 0.0
    if keys == ("revenue",):
        return row.get("revenue", 0)
    if len(keys) == 1:
        return row.get(keys[0], 0)
    return sum(_number(row.get(key, 0)) for key in keys)


def build_finance_telegram_message(*, company_name: str, row: FinanceRow) -> str:
    lines: list[str] = []
    for index, (label, keys) in enumerate(FINANCE_TELEGRAM_COLUMNS):
        if index in {3, 7}:
            lines.append("")
        value = _column_value(row, keys)
        lines.append(f"{label}: {_format_value(value, is_percent=keys in {('drr',), ('logistics_pct',)})}")
    return "\n".join(lines)


def _env_suffix(company_name: str) -> str:
    suffix = re.sub(r"[^A-Za-z0-9]+", "_", str(company_name or "").strip()).strip("_")
    return suffix.upper()


def resolve_company_chat_id(company_name: str, company_index: int, company_count: int) -> str:
    suffix = _env_suffix(company_name)
    for key in [f"TG_CHAT_ID_{suffix}", f"TELEGRAM_CHAT_ID_{suffix}"]:
        value = os.getenv(key, "").strip()
        if value:
            return value

    legacy_names = [
        (os.getenv("COMPANY_NAME", "").strip(), os.getenv("TG_CHAT_ID", "").strip()),
        (os.getenv("COMPANY_NAME_2", "").strip(), os.getenv("TG_CHAT_ID_2", "").strip()),
    ]
    for legacy_name, chat_id in legacy_names:
        if legacy_name and legacy_name == company_name and chat_id:
            return chat_id

    indexed_key = "TG_CHAT_ID" if company_index == 0 else f"TG_CHAT_ID_{company_index + 1}"
    indexed_value = os.getenv(indexed_key, "").strip()
    if indexed_value:
        return indexed_value

    if company_count == 1:
        return os.getenv("TG_CHAT_ID", "").strip()
    return ""


def _send_telegram_message(*, token: str, chat_id: str, text: str) -> None:
    response = requests.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        json={"chat_id": chat_id, "text": text},
        timeout=30,
    )
    response.raise_for_status()


def _iter_company_names() -> list[str]:
    configs = load_runtime_company_configs()
    if configs:
        return sorted(configs.keys())
    default_config = default_company_from_env()
    if any((default_config.get(key) or "").strip() for key in default_config):
        return ["default"]
    return []


def send_yesterday_finance_reports() -> None:
    token = os.getenv("TG_BOT_TOKEN", "").strip() or os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        logger.info("finance telegram scheduler skipped: missing TG_BOT_TOKEN")
        return

    tz = ZoneInfo(os.getenv("TZ", "Europe/Moscow"))
    yesterday = (datetime.now(tz).date() - timedelta(days=1)).isoformat()
    companies = _iter_company_names()
    if not companies:
        logger.info("finance telegram scheduler skipped: no companies configured")
        return

    for index, company_name in enumerate(companies):
        chat_id = resolve_company_chat_id(company_name, index, len(companies))
        if not chat_id:
            logger.info("finance telegram report skipped: no chat id", extra={"company": company_name})
            continue
        try:
            summary = get_finance_summary(company=company_name, date_from=yesterday, date_to=yesterday)
            rows = summary.get("rows", []) or []
            if not rows:
                logger.info("finance telegram report skipped: empty finance rows", extra={"company": company_name})
                continue
            message = build_finance_telegram_message(company_name=company_name, row=rows[0])
            _send_telegram_message(token=token, chat_id=chat_id, text=message)
            logger.info("finance telegram report sent", extra={"company": company_name, "day": yesterday})
        except Exception:
            logger.exception("finance telegram report failed", extra={"company": company_name})


def _seconds_until_next_run(now: datetime, target_hour: int = 8) -> float:
    target = now.replace(hour=target_hour, minute=0, second=0, microsecond=0)
    if now >= target:
        target += timedelta(days=1)
    return max(1.0, (target - now).total_seconds())


async def finance_telegram_scheduler_loop(timezone_name: str) -> None:
    try:
        tz = ZoneInfo(timezone_name)
    except Exception:
        logger.exception("invalid timezone for finance telegram scheduler", extra={"timezone": timezone_name})
        tz = ZoneInfo("Europe/Moscow")

    while True:
        now = datetime.now(tz)
        sleep_seconds = _seconds_until_next_run(now, target_hour=8)
        next_run = now + timedelta(seconds=sleep_seconds)
        logger.info("finance telegram scheduler sleeping", extra={"next_run": next_run.isoformat()})
        await asyncio.sleep(sleep_seconds)
        try:
            await asyncio.to_thread(send_yesterday_finance_reports)
        except Exception:
            logger.exception("finance telegram scheduler cycle failed")
