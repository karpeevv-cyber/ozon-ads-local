# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import logging
import os
from datetime import date, timedelta, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

from bid_changes import load_bid_changes
from clients_ads import perf_token, get_campaign_stats_json, get_campaigns
from clients_seller import seller_finance_balance
from clients_seller import seller_analytics_sku_day, seller_analytics_stocks
from ui_helpers import load_company_configs, default_company_from_env


LOG_PATH = Path("app.log")
logger = logging.getLogger("ozon_ads")
if not logger.handlers:
    logger.setLevel(logging.INFO)
    handler = logging.FileHandler(LOG_PATH, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logger.addHandler(handler)

TEST_META_PREFIX = "__test_meta__:"


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


def _chunks(items: list[str], size: int) -> list[list[str]]:
    if size <= 0:
        size = 1
    return [items[i:i + size] for i in range(0, len(items), size)]


def _to_float(value) -> float:
    if value is None:
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    try:
        text = str(value).strip().replace(" ", "").replace(",", ".")
        return float(text) if text else 0.0
    except Exception:
        return 0.0


def _row_spend_value(row: dict) -> float:
    direct = (
        _to_float(row.get("moneySpent"))
        or _to_float(row.get("money_spent"))
        or _to_float(row.get("spend"))
    )
    if direct > 0:
        return direct
    days = row.get("days")
    if isinstance(days, list):
        return sum(
            _to_float(d.get("moneySpent"))
            or _to_float(d.get("money_spent"))
            or _to_float(d.get("spend"))
            for d in days
            if isinstance(d, dict)
        )
    return 0.0


def _parse_test_comment_payload(comment: str) -> dict | None:
    text = str(comment or "").strip()
    if not text.startswith(TEST_META_PREFIX):
        return None
    try:
        raw = json.loads(text[len(TEST_META_PREFIX):])
    except Exception:
        return None
    start_date = str(raw.get("start_date", raw.get("date_from", "")) or "").strip()
    try:
        target_clicks = int(float(str(raw.get("target_clicks", 0)).strip().replace(",", ".")))
    except Exception:
        target_clicks = 0
    return {
        "start_date": start_date,
        "target_clicks": target_clicks,
        "essence": str(raw.get("essence", "") or "").strip(),
        "expectations": str(raw.get("expectations", "") or "").strip(),
        "note": str(raw.get("note", "") or "").strip(),
        "company": str(raw.get("company", "") or "").strip(),
    }


def _daterange_days(date_from_iso: str, date_to_iso: str) -> list[str]:
    try:
        d_from = date.fromisoformat(str(date_from_iso))
        d_to = date.fromisoformat(str(date_to_iso))
    except Exception:
        return []
    out: list[str] = []
    d = d_from
    while d <= d_to:
        out.append(d.isoformat())
        d += timedelta(days=1)
    return out


def _load_test_entries(*, company_name: str) -> list[dict]:
    df = load_bid_changes()
    if df is None or df.empty or "reason" not in df.columns:
        return []
    rows = df[df["reason"].astype(str) == "Test"].copy()
    if rows.empty:
        return []
    out: list[dict] = []
    for _, row in rows.iterrows():
        meta = _parse_test_comment_payload(row.get("comment", ""))
        if not meta:
            continue
        meta_company = str(meta.get("company", "") or "").strip()
        if meta_company and meta_company != str(company_name):
            continue
        out.append(
            {
                "ts_iso": str(row.get("ts_iso", "") or ""),
                "campaign_id": str(row.get("campaign_id", "") or ""),
                "sku": str(row.get("sku", "") or ""),
                **meta,
            }
        )
    out.sort(key=lambda x: str(x.get("ts_iso", "")), reverse=True)
    return out


def _build_test_daily_rows(
    *,
    campaign_id: str,
    sku: str,
    date_from_iso: str,
    date_to_iso: str,
    seller_client_id: str,
    seller_api_key: str,
    perf_client_id: str,
    perf_client_secret: str,
) -> list[dict]:
    days = _daterange_days(date_from_iso, date_to_iso)
    if not days:
        return []
    _by_sku, _by_day, by_day_sku = seller_analytics_sku_day(
        date_from_iso,
        date_to_iso,
        limit=1000,
        client_id=seller_client_id,
        api_key=seller_api_key,
    )
    token = perf_token(perf_client_id, perf_client_secret)
    stats = get_campaign_stats_json(token, date_from_iso, date_to_iso, [str(campaign_id)])
    rows_by_day: dict[str, dict] = {}
    for r in (stats.get("rows", []) or []):
        day_str = str(r.get("date") or r.get("day") or "")
        if day_str:
            rows_by_day[day_str] = r
    out: list[dict] = []
    for day_str in days:
        r = rows_by_day.get(day_str, {}) or {}
        views = int(round(float(r.get("views", 0) or 0)))
        clicks = int(round(float(r.get("clicks", 0) or 0)))
        money_spent = float(r.get("moneySpent", 0) or 0)
        click_price_api = float(r.get("clickPrice", 0) or 0)
        click_price = (money_spent / clicks) if clicks > 0 else click_price_api
        revenue, units = by_day_sku.get((day_str, str(sku)), (0.0, 0))
        revenue = float(revenue or 0)
        units = int(units or 0)
        ctr = (clicks / views * 100.0) if views else 0.0
        cr = (units / clicks * 100.0) if clicks else 0.0
        drr = (money_spent / revenue * 100.0) if revenue else 0.0
        out.append(
            {
                "day": day_str,
                "views": views,
                "clicks": clicks,
                "ctr": ctr,
                "cr": cr,
                "money_spent": money_spent,
                "click_price": click_price,
                "total_revenue": revenue,
                "total_drr_pct": drr,
                "ordered_units": units,
            }
        )
    return out


def _summarize_test_metrics(rows: list[dict]) -> dict[str, float]:
    views = sum(float(r.get("views", 0) or 0) for r in rows)
    clicks = sum(float(r.get("clicks", 0) or 0) for r in rows)
    money_spent = sum(float(r.get("money_spent", 0) or 0) for r in rows)
    revenue = sum(float(r.get("total_revenue", 0) or 0) for r in rows)
    units = sum(float(r.get("ordered_units", 0) or 0) for r in rows)
    return {
        "views": views,
        "clicks": clicks,
        "ctr": (clicks / views * 100.0) if views else 0.0,
        "cr": (units / clicks * 100.0) if clicks else 0.0,
        "money_spent": money_spent,
        "click_price": (money_spent / clicks) if clicks else 0.0,
        "total_revenue": revenue,
        "total_drr_pct": (money_spent / revenue * 100.0) if revenue else 0.0,
    }


def _evaluate_test_entry(
    entry: dict,
    *,
    seller_client_id: str,
    seller_api_key: str,
    perf_client_id: str,
    perf_client_secret: str,
) -> dict:
    start_date = str(entry.get("start_date", "") or "")
    target_clicks = int(entry.get("target_clicks", 0) or 0)
    live_rows = _build_test_daily_rows(
        campaign_id=str(entry.get("campaign_id", "")),
        sku=str(entry.get("sku", "")),
        date_from_iso=start_date,
        date_to_iso=date.today().isoformat(),
        seller_client_id=seller_client_id,
        seller_api_key=seller_api_key,
        perf_client_id=perf_client_id,
        perf_client_secret=perf_client_secret,
    )
    cum = 0
    completion_day = ""
    test_rows: list[dict] = []
    for row in live_rows:
        cum += int(row.get("clicks", 0) or 0)
        test_rows.append(row)
        if target_clicks > 0 and cum >= target_clicks and not completion_day:
            completion_day = str(row.get("day", "") or "")
            break
    status = "completed" if completion_day else "active"
    actual_clicks = sum(int(r.get("clicks", 0) or 0) for r in test_rows)
    baseline_summary = _summarize_test_metrics([])
    if status == "completed":
        baseline_end = date.fromisoformat(start_date) - timedelta(days=1)
        baseline_start = baseline_end - timedelta(days=180)
        baseline_rows_all = _build_test_daily_rows(
            campaign_id=str(entry.get("campaign_id", "")),
            sku=str(entry.get("sku", "")),
            date_from_iso=baseline_start.isoformat(),
            date_to_iso=baseline_end.isoformat(),
            seller_client_id=seller_client_id,
            seller_api_key=seller_api_key,
            perf_client_id=perf_client_id,
            perf_client_secret=perf_client_secret,
        )
        baseline_rows_all = list(reversed(baseline_rows_all))
        selected: list[dict] = []
        cum_prev = 0
        target_prev = max(actual_clicks, target_clicks)
        for row in baseline_rows_all:
            selected.append(row)
            cum_prev += int(row.get("clicks", 0) or 0)
            if target_prev > 0 and cum_prev >= target_prev:
                break
        baseline_summary = _summarize_test_metrics(list(reversed(selected)))
    return {
        "status": status,
        "completion_day": completion_day,
        "actual_clicks": actual_clicks,
        "test_summary": _summarize_test_metrics(test_rows),
        "baseline_summary": baseline_summary,
    }


def _load_article_map_for_skus(*, skus: list[str], seller_client_id: str, seller_api_key: str) -> dict[str, str]:
    if not skus:
        return {}
    resp = seller_analytics_stocks(
        skus=skus,
        client_id=seller_client_id,
        api_key=seller_api_key,
    )
    out: dict[str, str] = {}
    for it in (resp.get("items", []) or []):
        sku = str(it.get("sku", "") or "").strip()
        if sku:
            out[sku] = str(it.get("offer_id", "") or "").strip() or sku
    return out


def _fmt_int(value: float) -> str:
    try:
        return str(int(round(float(value))))
    except Exception:
        return "0"


def _fmt_rub(value: float) -> str:
    try:
        return f"{int(round(float(value)))} ₽"
    except Exception:
        return "0 ₽"


def _fmt_pct(value: float) -> str:
    try:
        return f"{float(value):.1f}%"
    except Exception:
        return "0.0%"


def _build_test_result_message(*, article: str, entry: dict, evaluation: dict) -> str:
    test_summary = evaluation.get("test_summary", {}) or {}
    control_summary = evaluation.get("baseline_summary", {}) or {}
    lines = [
        f"Test completed: {article}",
        f"Essence: {entry.get('essence', '')}",
        f"Started: {entry.get('start_date', '')}",
        f"Completed: {evaluation.get('completion_day', '')}",
        f"Target clicks: {_fmt_int(entry.get('target_clicks', 0))}",
        f"Actual clicks: {_fmt_int(evaluation.get('actual_clicks', 0))}",
        "",
        "Test:",
        f"views: {_fmt_int(test_summary.get('views', 0))}",
        f"clicks: {_fmt_int(test_summary.get('clicks', 0))}",
        f"ctr: {_fmt_pct(test_summary.get('ctr', 0))}",
        f"cr: {_fmt_pct(test_summary.get('cr', 0))}",
        f"money_spent: {_fmt_rub(test_summary.get('money_spent', 0))}",
        f"click_price: {_fmt_rub(test_summary.get('click_price', 0))}",
        f"total_revenue: {_fmt_rub(test_summary.get('total_revenue', 0))}",
        f"total_drr_pct: {_fmt_pct(test_summary.get('total_drr_pct', 0))}",
        "",
        "Control:",
        f"views: {_fmt_int(control_summary.get('views', 0))}",
        f"clicks: {_fmt_int(control_summary.get('clicks', 0))}",
        f"ctr: {_fmt_pct(control_summary.get('ctr', 0))}",
        f"cr: {_fmt_pct(control_summary.get('cr', 0))}",
        f"money_spent: {_fmt_rub(control_summary.get('money_spent', 0))}",
        f"click_price: {_fmt_rub(control_summary.get('click_price', 0))}",
        f"total_revenue: {_fmt_rub(control_summary.get('total_revenue', 0))}",
        f"total_drr_pct: {_fmt_pct(control_summary.get('total_drr_pct', 0))}",
    ]
    return "\n".join(lines)


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
    reverse_logistics = 0.0
    returns_processing = 0.0
    cross_docking = 0.0
    acceptance = 0.0
    errors = 0.0
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
        if name == "reverse_logistics":
            reverse_logistics += val
        if name == "partner_returns_cancellations_processing":
            returns_processing += val
        if name == "cross_docking":
            cross_docking += val
        if name == "goods_processing_in_shipment":
            acceptance += val
        if name == "booking_space_and_staff_for_partial_shipment":
            errors += val
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
        + reverse_logistics
        + returns_processing
        + cross_docking
        + acceptance
        + errors
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
        "обратная логистика": str(_ceil_int(reverse_logistics)),
        "возвраты": str(_ceil_int(returns_processing)),
        "кросс-докинг": str(_ceil_int(cross_docking)),
        "приемка": str(_ceil_int(acceptance)),
        "ошибки": str(_ceil_int(errors)),
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


def _load_main_day_metrics(
    day_iso: str,
    *,
    seller_client_id: str,
    seller_api_key: str,
    perf_client_id: str,
    perf_client_secret: str,
) -> dict[str, float]:
    _by_sku, by_day, _by_day_sku = seller_analytics_sku_day(
        day_iso,
        day_iso,
        limit=1000,
        client_id=seller_client_id,
        api_key=seller_api_key,
    )
    revenue, _units = by_day.get(day_iso, (0.0, 0))
    revenue = float(revenue or 0.0)
    if revenue <= 0:
        # Fallback: some responses may return a day key with time suffix.
        revenue = sum(
            float(v[0] or 0.0)
            for k, v in by_day.items()
            if str(k).startswith(day_iso)
        )
    if revenue <= 0:
        # Single-day request fallback: sum across all SKU totals.
        revenue = sum(float(v[0] or 0.0) for v in _by_sku.values())

    spend = 0.0
    try:
        token = perf_token(perf_client_id, perf_client_secret)
        campaigns = get_campaigns(token)
        running_ids = []
        for c in campaigns:
            cid = str(c.get("id") or "").strip()
            state = str(c.get("state") or "").upper()
            if cid and "RUNNING" in state:
                running_ids.append(cid)
        if not running_ids:
            running_ids = [str(c.get("id")) for c in campaigns if str(c.get("id") or "").strip()]
        if running_ids:
            for batch in _chunks(running_ids, 10):
                stats = get_campaign_stats_json(token, day_iso, day_iso, batch)
                for r in (stats.get("rows", []) or []):
                    if isinstance(r, dict):
                        spend += _row_spend_value(r)
    except Exception:
        logger.exception("Failed to load ads spend for main day metrics")
    drr_pct = (spend / revenue * 100.0) if revenue > 0 else 0.0
    return {"revenue": revenue, "drr_pct": drr_pct}


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
    perf_client_id = (creds.get("perf_client_id") or "").strip()
    perf_client_secret = (creds.get("perf_client_secret") or "").strip()
    if not seller_client_id or not seller_api_key or not perf_client_id or not perf_client_secret:
        logger.error("Missing seller/perf creds")
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
    main_metrics = _load_main_day_metrics(
        yesterday,
        seller_client_id=seller_client_id,
        seller_api_key=seller_api_key,
        perf_client_id=perf_client_id,
        perf_client_secret=perf_client_secret,
    )
    row["Revenue"] = str(_ceil_int(main_metrics.get("revenue", 0.0)))
    row["drr"] = f"{float(main_metrics.get('drr_pct', 0.0) or 0.0):.1f}"

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
        "обратная логистика",
        "возвраты",
        "кросс-докинг",
        "приемка",
        "ошибки",
        "Хранение",
        "реклама",
        "реклама - за заказ",
        "баллы за отзывы",
        "бонусы продавца",
        "проверка",
        "% логистики",
    ]
    ordered_keys = [ordered_keys[0], "Revenue", "drr", *ordered_keys[1:]]
    lines = [f"{k}: {row.get(k, '')}" for k in ordered_keys]
    if len(lines) >= 3:
        lines.insert(3, "")
    if len(lines) >= 7:
        lines.insert(7, "")
    text = "\n".join(lines)
    _send_telegram_message(token, chat_id, text)

    try:
        test_entries = _load_test_entries(company_name=str(company_name or ""))
        completed_yesterday = []
        for entry in test_entries:
            eval_res = _evaluate_test_entry(
                entry,
                seller_client_id=seller_client_id,
                seller_api_key=seller_api_key,
                perf_client_id=perf_client_id,
                perf_client_secret=perf_client_secret,
            )
            if str(eval_res.get("completion_day", "")) == yesterday:
                completed_yesterday.append((entry, eval_res))
        if completed_yesterday:
            article_map = _load_article_map_for_skus(
                skus=[str(entry.get("sku", "")) for entry, _ in completed_yesterday],
                seller_client_id=seller_client_id,
                seller_api_key=seller_api_key,
            )
            for entry, eval_res in completed_yesterday:
                article = article_map.get(str(entry.get("sku", "")), str(entry.get("sku", "")))
                msg = _build_test_result_message(article=article, entry=entry, evaluation=eval_res)
                _send_telegram_message(token, chat_id, msg)
    except Exception:
        logger.exception("Failed to send completed test notifications")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
