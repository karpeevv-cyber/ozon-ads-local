from __future__ import annotations

import asyncio
import json
import logging
import os
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import requests
from sqlalchemy.orm import Session

from app.db.bootstrap import create_all
from app.db.session import SessionLocal
from app.models.campaign_hourly import CampaignHourlySnapshot
from app.services.campaign_reporting import fetch_ads_stats_by_campaign_from_credentials, parse_money
from app.services.company_config import default_company_from_env, load_runtime_company_configs, resolve_company_config
from app.services.integrations.ozon_ads import get_campaign_products_all, get_running_campaigns, perf_token
from app.services.integrations.ozon_seller import seller_posting_fbo_list

logger = logging.getLogger("uvicorn.error")


@dataclass(frozen=True)
class HourlyCompanyConfig:
    name: str
    perf_client_id: str
    perf_client_secret: str


def _iter_company_configs() -> list[HourlyCompanyConfig]:
    configs = load_runtime_company_configs()
    if not configs:
        configs = {"default": default_company_from_env()}
    result: list[HourlyCompanyConfig] = []
    for company_name, config in sorted(configs.items()):
        perf_client_id = (config.get("perf_client_id") or "").strip()
        perf_client_secret = (config.get("perf_client_secret") or "").strip()
        if not perf_client_id or not perf_client_secret:
            continue
        result.append(HourlyCompanyConfig(company_name, perf_client_id, perf_client_secret))
    return result


def _to_moscow_naive(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(ZoneInfo("Europe/Moscow")).replace(tzinfo=None)


def _upsert_snapshot(
    db: Session,
    *,
    company: str,
    campaign_id: str,
    campaign_title: str,
    day: date,
    sample_hour: int,
    sample_at: datetime,
    views: int,
    clicks: int,
    money_spent: float,
    raw_ads_json: dict,
) -> None:
    existing = (
        db.query(CampaignHourlySnapshot)
        .filter(
            CampaignHourlySnapshot.company == company,
            CampaignHourlySnapshot.campaign_id == str(campaign_id),
            CampaignHourlySnapshot.day == day,
            CampaignHourlySnapshot.sample_hour == int(sample_hour),
        )
        .one_or_none()
    )
    if existing is None:
        db.add(
            CampaignHourlySnapshot(
                company=company,
                campaign_id=str(campaign_id),
                campaign_title=campaign_title,
                day=day,
                sample_hour=int(sample_hour),
                sample_at=sample_at,
                views=int(views),
                clicks=int(clicks),
                money_spent=float(money_spent),
                raw_ads_json=json.dumps(raw_ads_json, ensure_ascii=False),
            )
        )
        return
    existing.campaign_title = campaign_title
    existing.sample_at = sample_at
    existing.views = int(views)
    existing.clicks = int(clicks)
    existing.money_spent = float(money_spent)
    existing.raw_ads_json = json.dumps(raw_ads_json, ensure_ascii=False)


def collect_campaign_hourly_snapshot_for_company(
    *,
    db: Session,
    company: str,
    perf_client_id: str,
    perf_client_secret: str,
    now: datetime | None = None,
) -> int:
    create_all()
    tz = ZoneInfo(os.getenv("TZ", "Europe/Moscow"))
    now_value = now or datetime.now(tz)
    if now_value.tzinfo is None:
        now_value = now_value.replace(tzinfo=tz)
    sample_hour = now_value.hour
    sample_at = _to_moscow_naive(now_value)

    try:
        campaigns = get_running_campaigns(client_id=perf_client_id, client_secret=perf_client_secret)
    except requests.HTTPError as exc:
        if exc.response is not None and exc.response.status_code == 429:
            logger.warning("campaign hourly snapshot skipped due to upstream 429", extra={"company": company})
            return 0
        raise
    campaign_ids = [str(item.get("id")) for item in campaigns if item.get("id") is not None]
    if not campaign_ids:
        return 0

    titles = {str(item.get("id")): str(item.get("title") or "") for item in campaigns}
    def save_day_snapshot(target_day: date, target_hour: int) -> int:
        stats_by_campaign = fetch_ads_stats_by_campaign_from_credentials(
            perf_client_id=perf_client_id,
            perf_client_secret=perf_client_secret,
            date_from=target_day.isoformat(),
            date_to=target_day.isoformat(),
            running_ids=campaign_ids,
            batch_size=15,
        )
        saved_count = 0
        for target_campaign_id in campaign_ids:
            row = stats_by_campaign.get(str(target_campaign_id), {}) or {}
            _upsert_snapshot(
                db,
                company=company,
                campaign_id=str(target_campaign_id),
                campaign_title=titles.get(str(target_campaign_id), ""),
                day=target_day,
                sample_hour=target_hour,
                sample_at=sample_at,
                views=int(parse_money(row.get("views"))),
                clicks=int(parse_money(row.get("clicks"))),
                money_spent=float(parse_money(row.get("moneySpent"))),
                raw_ads_json=row,
            )
            saved_count += 1
        return saved_count

    saved = 0
    saved += save_day_snapshot(now_value.date(), sample_hour)
    if sample_hour == 0:
        saved += save_day_snapshot(now_value.date() - timedelta(days=1), 24)
    db.commit()
    return saved


def collect_campaign_hourly_snapshots_for_all_companies(now: datetime | None = None) -> int:
    companies = _iter_company_configs()
    if not companies:
        logger.info("campaign hourly snapshot skipped: no companies configured")
        return 0
    total = 0
    for config in companies:
        db = SessionLocal()
        try:
            total += collect_campaign_hourly_snapshot_for_company(
                db=db,
                company=config.name,
                perf_client_id=config.perf_client_id,
                perf_client_secret=config.perf_client_secret,
                now=now,
            )
            logger.info("campaign hourly snapshot collected", extra={"company": config.name})
        except Exception:
            db.rollback()
            logger.exception("campaign hourly snapshot failed", extra={"company": config.name})
        finally:
            db.close()
    return total


def _snapshot_payload(snapshot: CampaignHourlySnapshot | None) -> dict | None:
    if snapshot is None:
        return None
    raw_payload = _snapshot_raw(snapshot)
    return {
        "sample_hour": snapshot.sample_hour,
        "sample_at": snapshot.sample_at.isoformat() if snapshot.sample_at else None,
        "views": snapshot.views,
        "clicks": snapshot.clicks,
        "money_spent": snapshot.money_spent,
        "orders": int(parse_money(raw_payload.get("orders"))),
    }


def _snapshot_raw(snapshot: CampaignHourlySnapshot | None) -> dict:
    if snapshot is None:
        return {}
    try:
        raw = json.loads(snapshot.raw_ads_json or "{}")
    except Exception:
        return {}
    return raw if isinstance(raw, dict) else {}


def _ads_orders_delta(start_sample: CampaignHourlySnapshot | None, end_sample: CampaignHourlySnapshot | None) -> int:
    if start_sample is None or end_sample is None:
        return 0
    start_raw = _snapshot_raw(start_sample)
    end_raw = _snapshot_raw(end_sample)
    return max(0, int(parse_money(end_raw.get("orders")) - parse_money(start_raw.get("orders"))))


def _extract_postings(payload: dict) -> list[dict]:
    result = payload.get("result") if isinstance(payload, dict) else None
    if isinstance(result, list):
        return [item for item in result if isinstance(item, dict)]
    if isinstance(result, dict):
        postings = result.get("postings") or result.get("items") or []
        return [item for item in postings if isinstance(item, dict)]
    postings = payload.get("postings") if isinstance(payload, dict) else []
    return [item for item in postings if isinstance(item, dict)]


def _parse_datetime(value: str, tz: ZoneInfo) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=tz)
    return parsed.astimezone(tz)


def _campaign_skus(
    *,
    campaign_id: str,
    perf_client_id: str | None,
    perf_client_secret: str | None,
) -> list[str]:
    if not campaign_id:
        return []
    token = perf_token(client_id=perf_client_id, client_secret=perf_client_secret)
    products = get_campaign_products_all(token, campaign_id)
    skus = sorted({str(item.get("sku") or "").strip() for item in products if str(item.get("sku") or "").strip()})
    return skus


def _total_fbo_orders_by_hour(
    *,
    target_day: date,
    skus: list[str],
    seller_client_id: str | None,
    seller_api_key: str | None,
    timezone_name: str = "Europe/Moscow",
) -> dict[int, int]:
    if not skus or not seller_client_id or not seller_api_key:
        return {}
    tz = ZoneInfo(timezone_name)
    sku_set = {str(sku) for sku in skus}
    since_local = datetime(target_day.year, target_day.month, target_day.day, tzinfo=tz)
    to_local = since_local + timedelta(days=1)
    since_utc = since_local.astimezone(ZoneInfo("UTC")).isoformat().replace("+00:00", "Z")
    to_utc = to_local.astimezone(ZoneInfo("UTC")).isoformat().replace("+00:00", "Z")

    orders_by_hour: dict[int, int] = {}
    offset = 0
    limit = 1000
    while True:
        payload = seller_posting_fbo_list(
            since=since_utc,
            to=to_utc,
            limit=limit,
            offset=offset,
            client_id=seller_client_id,
            api_key=seller_api_key,
        )
        postings = _extract_postings(payload)
        if not postings:
            break
        for posting in postings:
            status = str(posting.get("status") or "").lower()
            if "cancel" in status:
                continue
            created_at = _parse_datetime(str(posting.get("created_at") or posting.get("in_process_at") or ""), tz)
            if created_at is None or created_at.date() != target_day:
                continue
            quantity = 0
            for product in posting.get("products") or []:
                sku = str(product.get("sku") or "").strip()
                if sku not in sku_set:
                    continue
                try:
                    quantity += int(float(str(product.get("quantity") or 0).replace(",", ".")))
                except Exception:
                    continue
            if quantity > 0:
                orders_by_hour[created_at.hour] = orders_by_hour.get(created_at.hour, 0) + quantity
        if len(postings) < limit:
            break
        offset += limit
    return orders_by_hour


def get_campaign_hourly_report(
    *,
    db: Session,
    company: str | None,
    day: str,
    campaign_id: str | None = None,
) -> dict:
    create_all()
    company_name, config = resolve_company_config(company)
    perf_client_id = (config.get("perf_client_id") or "").strip() or None
    perf_client_secret = (config.get("perf_client_secret") or "").strip() or None
    seller_client_id = (config.get("seller_client_id") or "").strip() or None
    seller_api_key = (config.get("seller_api_key") or "").strip() or None

    try:
        campaigns = get_running_campaigns(client_id=perf_client_id, client_secret=perf_client_secret)
    except requests.HTTPError as exc:
        if exc.response is None or exc.response.status_code != 429:
            raise
        campaigns = []
    campaign_options = [
        {
            "campaign_id": str(item.get("id") or ""),
            "title": str(item.get("title") or ""),
            "state": str(item.get("state") or ""),
        }
        for item in campaigns
        if item.get("id") is not None
    ]
    if campaign_id:
        selected_campaign_id = str(campaign_id)
    elif campaign_options:
        selected_campaign_id = str(campaign_options[0]["campaign_id"])
    else:
        selected_campaign_id = ""
    title_by_id = {item["campaign_id"]: item["title"] for item in campaign_options}

    target_day = date.fromisoformat(str(day))
    snapshots = (
        db.query(CampaignHourlySnapshot)
        .filter(
            CampaignHourlySnapshot.company == company_name,
            CampaignHourlySnapshot.campaign_id == selected_campaign_id,
            CampaignHourlySnapshot.day == target_day,
        )
        .order_by(CampaignHourlySnapshot.sample_hour.asc(), CampaignHourlySnapshot.sample_at.asc())
        .all()
    )
    latest_by_hour: dict[int, CampaignHourlySnapshot] = {}
    for snapshot in snapshots:
        latest_by_hour[int(snapshot.sample_hour)] = snapshot

    total_orders_by_hour: dict[int, int] = {}
    try:
        campaign_skus = _campaign_skus(
            campaign_id=selected_campaign_id,
            perf_client_id=perf_client_id,
            perf_client_secret=perf_client_secret,
        )
        total_orders_by_hour = _total_fbo_orders_by_hour(
            target_day=target_day,
            skus=campaign_skus,
            seller_client_id=seller_client_id,
            seller_api_key=seller_api_key,
            timezone_name=os.getenv("TZ", "Europe/Moscow"),
        )
    except Exception:
        logger.exception(
            "campaign hourly total seller orders failed",
            extra={"company": company_name, "campaign_id": selected_campaign_id},
        )

    rows: list[dict] = []
    for hour in range(24):
        start_sample = latest_by_hour.get(hour)
        end_sample = latest_by_hour.get(hour + 1)
        has_data = start_sample is not None and end_sample is not None
        views = max(0, int(end_sample.views - start_sample.views)) if has_data else 0
        clicks = max(0, int(end_sample.clicks - start_sample.clicks)) if has_data else 0
        money_spent = max(0.0, float(end_sample.money_spent - start_sample.money_spent)) if has_data else 0.0
        orders = int(total_orders_by_hour.get(hour, 0))
        if not total_orders_by_hour:
            orders = _ads_orders_delta(start_sample, end_sample) if has_data else 0
        rows.append(
            {
                "hour": hour,
                "label": f"{hour:02d}:00",
                "views": views,
                "clicks": clicks,
                "orders": orders,
                "money_spent": round(money_spent, 2),
                "has_data": has_data,
                "start_sample": _snapshot_payload(start_sample),
                "end_sample": _snapshot_payload(end_sample),
            }
        )

    return {
        "company": company_name,
        "day": target_day.isoformat(),
        "campaigns": campaign_options,
        "selected_campaign_id": selected_campaign_id,
        "selected_campaign_title": title_by_id.get(selected_campaign_id, ""),
        "last_sample_at": max((snapshot.sample_at for snapshot in latest_by_hour.values()), default=None).isoformat()
        if latest_by_hour
        else None,
        "rows": rows,
    }


def _seconds_until_next_hour_sample(now: datetime, delay_minutes: int) -> float:
    delay = timedelta(minutes=max(0, delay_minutes))
    next_sample = now.replace(minute=0, second=0, microsecond=0) + delay
    if next_sample <= now:
        next_sample += timedelta(hours=1)
    return max(1.0, (next_sample - now).total_seconds())


async def campaign_hourly_scheduler_loop(timezone_name: str) -> None:
    enabled = os.getenv("CAMPAIGN_HOURLY_ENABLED", "1").strip().lower() in {"1", "true", "yes", "on"}
    if not enabled:
        logger.info("campaign hourly scheduler disabled")
        return
    try:
        tz = ZoneInfo(timezone_name)
    except Exception:
        logger.exception("invalid timezone for campaign hourly scheduler", extra={"timezone": timezone_name})
        tz = ZoneInfo("Europe/Moscow")
    try:
        delay_minutes = int(os.getenv("CAMPAIGN_HOURLY_DELAY_MINUTES", "10"))
    except ValueError:
        delay_minutes = 10

    while True:
        now = datetime.now(tz)
        sleep_seconds = _seconds_until_next_hour_sample(now, delay_minutes)
        logger.info("campaign hourly scheduler sleeping", extra={"next_run": (now + timedelta(seconds=sleep_seconds)).isoformat()})
        await asyncio.sleep(sleep_seconds)
        try:
            await asyncio.to_thread(collect_campaign_hourly_snapshots_for_all_companies)
        except Exception:
            logger.exception("campaign hourly scheduler cycle failed")
