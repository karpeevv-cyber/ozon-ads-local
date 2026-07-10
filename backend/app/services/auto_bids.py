from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import requests

from app.services.bid_commands import apply_bid_command
from app.services.bid_history import load_bid_changes
from app.services.campaign_reporting import (
    build_report_rows,
    fetch_ads_stats_by_campaign_from_credentials,
    load_products_parallel,
    parse_money,
)
from app.services.company_config import default_company_from_env, load_runtime_company_configs
from app.services.finance_telegram import resolve_company_chat_id
from app.services.integrations.ozon_ads import get_running_campaigns, perf_token
from app.services.integrations.ozon_seller import seller_analytics_sku_day, seller_analytics_stocks
from app.services.storage_paths import backend_data_path

logger = logging.getLogger("uvicorn.error")

AUTO_REASON_PREFIX = "Auto bid"


@dataclass(frozen=True)
class CompanyAutoBidConfig:
    name: str
    perf_client_id: str
    perf_client_secret: str
    seller_client_id: str
    seller_api_key: str
    chat_id: str


@dataclass
class BidDecision:
    company: str
    day: str
    campaign_id: str
    sku: str
    article: str
    ad_spend: float
    total_revenue: float
    ordered_units: int
    drr_pct: float | None
    old_bid_rub: float | None
    new_bid_rub: float | None
    reason: str
    action: str
    manual_review: bool = False
    applied: bool = False
    skipped_duplicate: bool = False
    error: str = ""


def _iter_company_configs() -> list[CompanyAutoBidConfig]:
    configs = load_runtime_company_configs()
    if configs:
        items = sorted(configs.items())
    else:
        items = _legacy_env_company_items()
        if not items:
            items = [("default", default_company_from_env())]

    companies: list[CompanyAutoBidConfig] = []
    for index, (company_name, config) in enumerate(items):
        perf_client_id = (config.get("perf_client_id") or "").strip()
        perf_client_secret = (config.get("perf_client_secret") or "").strip()
        seller_client_id = (config.get("seller_client_id") or "").strip()
        seller_api_key = (config.get("seller_api_key") or "").strip()
        if not all([perf_client_id, perf_client_secret, seller_client_id, seller_api_key]):
            logger.info("auto bids skipped: incomplete company credentials", extra={"company": company_name})
            continue
        chat_id = resolve_company_chat_id(company_name, index, len(items))
        companies.append(
            CompanyAutoBidConfig(
                name=company_name,
                perf_client_id=perf_client_id,
                perf_client_secret=perf_client_secret,
                seller_client_id=seller_client_id,
                seller_api_key=seller_api_key,
                chat_id=chat_id,
            )
        )
    return companies


def _legacy_env_company_items() -> list[tuple[str, dict[str, str]]]:
    first_name = os.getenv("COMPANY_NAME", "").strip() or "default"
    items: list[tuple[str, dict[str, str]]] = []
    first = default_company_from_env()
    if any((first.get(key) or "").strip() for key in first):
        items.append((first_name, first))

    second_name = os.getenv("COMPANY_NAME_2", "").strip()
    second = {
        "perf_client_id": os.getenv("PERF_CLIENT_ID_2", ""),
        "perf_client_secret": os.getenv("PERF_CLIENT_SECRET_2", ""),
        "seller_client_id": os.getenv("SELLER_CLIENT_ID_2", ""),
        "seller_api_key": os.getenv("SELLER_API_KEY_2", ""),
    }
    if second_name and any((second.get(key) or "").strip() for key in second):
        items.append((second_name, second))
    return items


def _round_bid(value: float) -> float:
    return round(float(value), 1)


def _decide_bid(
    *,
    company: str,
    day: str,
    row: dict,
) -> BidDecision:
    spend = parse_money(row.get("money_spent"))
    revenue = parse_money(row.get("total_revenue"))
    ordered_units = int(parse_money(row.get("ordered_units")))
    old_bid = parse_money(row.get("bid"))
    drr_pct = (spend / revenue * 100.0) if revenue > 0 else None
    campaign_id = str(row.get("campaign_id") or "").strip()
    sku = str(row.get("sku") or "").strip()
    article = str(row.get("article") or row.get("title") or sku or "-").strip() or "-"

    base = BidDecision(
        company=company,
        day=day,
        campaign_id=campaign_id,
        sku=sku,
        article=article,
        ad_spend=spend,
        total_revenue=revenue,
        ordered_units=ordered_units,
        drr_pct=drr_pct,
        old_bid_rub=old_bid if old_bid > 0 else None,
        new_bid_rub=None,
        reason="",
        action="none",
    )

    if not campaign_id or not sku or sku == "several":
        base.manual_review = True
        base.reason = "Кампания содержит несколько SKU или SKU не определен"
        return base
    if old_bid <= 0:
        base.manual_review = True
        base.reason = "Текущая ставка не определена"
        return base

    if spend < 50:
        base.new_bid_rub = _round_bid(old_bid * 1.2)
        base.reason = "Расход менее 50 ₽ — недостаточный объем рекламного трафика"
        base.action = "increase"
        return base

    if spend <= 150:
        base.reason = "Расход находится в допустимом диапазоне 50–150 ₽"
        return base

    if spend <= 250:
        if ordered_units <= 0 or revenue <= 0:
            base.new_bid_rub = _round_bid(old_bid * 0.9)
            base.reason = "Расход выше 150 ₽ без заказов"
            base.action = "decrease"
            return base
        if drr_pct is not None and drr_pct > 25:
            base.new_bid_rub = _round_bid(old_bid * 0.9)
            base.reason = "Расход 150–250 ₽, ДРР выше 25%"
            base.action = "decrease"
            return base
        base.reason = "Расход 150–250 ₽, ДРР не превышает 25%"
        return base

    base.manual_review = True
    base.reason = "Расход выше 250 ₽ — нужен ручной разбор"
    return base


def _load_already_applied(day: str) -> set[tuple[str, str]]:
    path = str(backend_data_path("bid_changes.csv"))
    try:
        df = load_bid_changes(path)
    except Exception:
        logger.exception("auto bids failed to load bid history")
        return set()
    if df.empty:
        return set()
    reason_prefix = f"{AUTO_REASON_PREFIX} {day}:"
    rows = df[df["reason"].astype(str).str.startswith(reason_prefix, na=False)].copy()
    return {
        (str(row.get("campaign_id") or ""), str(row.get("sku") or ""))
        for _, row in rows.iterrows()
    }


def _fetch_sku_offer_map(
    *,
    skus: list[str],
    seller_client_id: str,
    seller_api_key: str,
) -> dict[str, str]:
    output: dict[str, str] = {}
    for index in range(0, len(skus), 200):
        batch = skus[index : index + 200]
        response = seller_analytics_stocks(
            skus=batch,
            client_id=seller_client_id,
            api_key=seller_api_key,
        )
        for item in response.get("items", []) or []:
            sku = str(item.get("sku") or "").strip()
            if sku:
                output[sku] = str(item.get("offer_id") or "").strip()
    return output


def build_company_bid_decisions(*, config: CompanyAutoBidConfig, day: str) -> list[BidDecision]:
    running_campaigns = get_running_campaigns(
        client_id=config.perf_client_id,
        client_secret=config.perf_client_secret,
    )
    running_ids = [str(campaign.get("id")) for campaign in running_campaigns if campaign.get("id") is not None]
    if not running_ids:
        return []

    by_sku, _by_day, _by_day_sku = seller_analytics_sku_day(
        day,
        day,
        limit=1000,
        client_id=config.seller_client_id,
        api_key=config.seller_api_key,
    )
    stats_by_campaign_id = fetch_ads_stats_by_campaign_from_credentials(
        perf_client_id=config.perf_client_id,
        perf_client_secret=config.perf_client_secret,
        date_from=day,
        date_to=day,
        running_ids=running_ids,
        batch_size=15,
    )
    token = perf_token(client_id=config.perf_client_id, client_secret=config.perf_client_secret)
    products_by_campaign_id = load_products_parallel(token, running_ids, page_size=100)
    campaign_skus = sorted(
        {
            str(item.get("sku")).strip()
            for items in products_by_campaign_id.values()
            for item in (items or [])
            if str(item.get("sku") or "").strip().isdigit()
        }
    )
    sku_offer_map = _fetch_sku_offer_map(
        skus=campaign_skus,
        seller_client_id=config.seller_client_id,
        seller_api_key=config.seller_api_key,
    )
    rows, _grand_total = build_report_rows(
        running_campaigns=running_campaigns,
        stats_by_campaign_id=stats_by_campaign_id,
        sales_map=by_sku,
        products_by_campaign_id=products_by_campaign_id,
        sku_offer_map=sku_offer_map,
        target_drr=0.2,
    )
    return [
        _decide_bid(company=config.name, day=day, row=row)
        for row in rows
        if str(row.get("campaign_id") or "") != "GRAND_TOTAL"
    ]


def _apply_decisions(*, decisions: list[BidDecision], dry_run: bool) -> None:
    if dry_run:
        return

    already_applied = _load_already_applied(decisions[0].day) if decisions else set()
    for decision in decisions:
        if decision.new_bid_rub is None or decision.manual_review:
            continue
        key = (decision.campaign_id, decision.sku)
        if key in already_applied:
            decision.skipped_duplicate = True
            continue
        try:
            apply_bid_command(
                company=decision.company,
                campaign_id=decision.campaign_id,
                sku=decision.sku,
                bid_rub=float(decision.new_bid_rub),
                reason=f"{AUTO_REASON_PREFIX} {decision.day}: {decision.reason}",
                comment="",
            )
            decision.applied = True
            already_applied.add(key)
        except Exception as exc:
            decision.error = str(exc)
            logger.exception(
                "auto bid apply failed",
                extra={"company": decision.company, "campaign_id": decision.campaign_id, "sku": decision.sku},
            )


def _fmt_rub(value: float | None) -> str:
    if value is None:
        return "N/A"
    return f"{int(round(float(value)))} ₽"


def _fmt_bid(value: float | None) -> str:
    if value is None:
        return "N/A"
    return f"{float(value):.1f}".rstrip("0").rstrip(".")


def _fmt_drr(value: float | None) -> str:
    if value is None:
        return "N/A"
    return f"{float(value):.1f}%"


def build_telegram_message(*, company: str, day: str, decisions: list[BidDecision], dry_run: bool) -> str:
    changed = [item for item in decisions if item.new_bid_rub is not None and not item.manual_review]
    manual = [item for item in decisions if item.manual_review]
    errors = [item for item in decisions if item.error]

    lines: list[str] = []
    if dry_run:
        lines.append("тест")
    lines.append(f"Автоставки Ozon Ads за {day}")
    lines.append(f"Компания: {company}")
    lines.append("")

    if changed:
        lines.append("Изменения:")
        for item in changed:
            status = ""
            if item.skipped_duplicate:
                status = " (уже применялось ранее)"
            elif not dry_run:
                status = " (применено)" if item.applied else " (не применено)"
            lines.extend(
                [
                    f"- {item.article}",
                    f"  расход: {_fmt_rub(item.ad_spend)}",
                    f"  заказы total: {_fmt_rub(item.total_revenue)}",
                    f"  дрр: {_fmt_drr(item.drr_pct)}",
                    f"  ставка: {_fmt_bid(item.old_bid_rub)} -> {_fmt_bid(item.new_bid_rub)}{status}",
                    f"  причина: {item.reason}",
                ]
            )
    else:
        lines.append("Изменений ставок нет.")

    if manual:
        lines.append("")
        lines.append("РУЧНОЙ РАЗБОР:")
        for item in manual:
            lines.extend(
                [
                    f"- {item.article}",
                    f"  расход: {_fmt_rub(item.ad_spend)}",
                    f"  заказы total: {_fmt_rub(item.total_revenue)}",
                    f"  дрр: {_fmt_drr(item.drr_pct)}",
                    f"  причина: {item.reason}",
                ]
            )

    if errors:
        lines.append("")
        lines.append("Ошибки применения:")
        for item in errors:
            lines.append(f"- {item.article}: {item.error}")

    return "\n".join(lines)


def _send_telegram_message(*, token: str, chat_id: str, text: str) -> None:
    response = requests.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        json={"chat_id": chat_id, "text": text},
        timeout=30,
    )
    response.raise_for_status()


def run_auto_bids_for_yesterday(*, dry_run: bool = False, send_telegram: bool = True) -> list[BidDecision]:
    token = os.getenv("TG_BOT_TOKEN", "").strip() or os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    tz = ZoneInfo(os.getenv("TZ", "Europe/Moscow"))
    day = (datetime.now(tz).date() - timedelta(days=1)).isoformat()
    all_decisions: list[BidDecision] = []

    companies = _iter_company_configs()
    if not companies:
        logger.info("auto bids skipped: no companies configured")
        return []

    for config in companies:
        try:
            decisions = build_company_bid_decisions(config=config, day=day)
            _apply_decisions(decisions=decisions, dry_run=dry_run)
            all_decisions.extend(decisions)
            if send_telegram:
                if not token:
                    logger.info("auto bids telegram skipped: missing TG_BOT_TOKEN")
                elif not config.chat_id:
                    logger.info("auto bids telegram skipped: missing chat id", extra={"company": config.name})
                else:
                    message = build_telegram_message(
                        company=config.name,
                        day=day,
                        decisions=decisions,
                        dry_run=dry_run,
                    )
                    _send_telegram_message(token=token, chat_id=config.chat_id, text=message)
            logger.info(
                "auto bids finished",
                extra={"company": config.name, "day": day, "dry_run": dry_run, "decisions": len(decisions)},
            )
        except Exception:
            logger.exception("auto bids failed", extra={"company": config.name, "day": day})
            if send_telegram and token and config.chat_id:
                _send_telegram_message(
                    token=token,
                    chat_id=config.chat_id,
                    text=(
                        ("тест\n" if dry_run else "")
                        + f"Автоставки Ozon Ads за {day}\n"
                        + f"Компания: {config.name}\n\n"
                        + "Ошибка расчета автоставок. Проверь backend logs."
                    ),
                )
    return all_decisions


def _seconds_until_next_run(now: datetime, target_hour: int = 9) -> float:
    target = now.replace(hour=target_hour, minute=0, second=0, microsecond=0)
    if now >= target:
        target += timedelta(days=1)
    return max(1.0, (target - now).total_seconds())


async def auto_bids_scheduler_loop(timezone_name: str) -> None:
    enabled = os.getenv("AUTO_BIDS_ENABLED", "1").strip().lower() in {"1", "true", "yes", "on"}
    if not enabled:
        logger.info("auto bids scheduler disabled")
        return
    try:
        tz = ZoneInfo(timezone_name)
    except Exception:
        logger.exception("invalid timezone for auto bids scheduler", extra={"timezone": timezone_name})
        tz = ZoneInfo("Europe/Moscow")

    while True:
        now = datetime.now(tz)
        sleep_seconds = _seconds_until_next_run(now, target_hour=int(os.getenv("AUTO_BIDS_HOUR", "9")))
        logger.info("auto bids scheduler sleeping", extra={"next_run": (now + timedelta(seconds=sleep_seconds)).isoformat()})
        await asyncio.sleep(sleep_seconds)
        try:
            await asyncio.to_thread(run_auto_bids_for_yesterday, dry_run=False, send_telegram=True)
        except Exception:
            logger.exception("auto bids scheduler cycle failed")
