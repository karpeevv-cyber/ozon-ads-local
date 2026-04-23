from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from app.db.session import SessionLocal
from app.services.company_config import default_company_from_env, load_company_configs
from app.services.shipment_history import rebuild_shipment_history_from_api

logger = logging.getLogger(__name__)


def _iter_company_credentials() -> list[tuple[str, str, str]]:
    configs = load_company_configs()
    if configs:
        items = sorted(configs.items())
    else:
        items = [("default", default_company_from_env())]
    result: list[tuple[str, str, str]] = []
    for company_name, config in items:
        seller_client_id = (config.get("seller_client_id") or "").strip()
        seller_api_key = (config.get("seller_api_key") or "").strip()
        if not seller_client_id or not seller_api_key:
            continue
        result.append((company_name, seller_client_id, seller_api_key))
    return result


def refresh_shipment_history_for_all_companies() -> None:
    companies = _iter_company_credentials()
    if not companies:
        logger.info("shipment_history scheduler skipped: no seller credentials configured")
        return

    total_rows = 0
    for company_name, seller_client_id, seller_api_key in companies:
        db = SessionLocal()
        try:
            rows = rebuild_shipment_history_from_api(
                db,
                company_name=company_name,
                seller_client_id=seller_client_id,
                seller_api_key=seller_api_key,
            )
            total_rows += rows
            logger.info(
                "shipment_history refreshed",
                extra={"company": company_name, "rows": rows},
            )
        except Exception:
            logger.exception("shipment_history refresh failed", extra={"company": company_name})
        finally:
            db.close()

    logger.info(
        "shipment_history scheduler cycle finished",
        extra={"companies": len(companies), "rows_total": total_rows},
    )


def _seconds_until_next_run(now: datetime, target_hour: int = 5) -> float:
    target = now.replace(hour=target_hour, minute=0, second=0, microsecond=0)
    if now >= target:
        target = target + timedelta(days=1)
    delta = target - now
    return max(1.0, delta.total_seconds())


async def shipment_history_scheduler_loop(timezone_name: str) -> None:
    try:
        tz = ZoneInfo(timezone_name)
    except Exception:
        logger.exception("invalid timezone for shipment_history scheduler", extra={"timezone": timezone_name})
        tz = ZoneInfo("UTC")
    while True:
        now = datetime.now(tz)
        sleep_seconds = _seconds_until_next_run(now, target_hour=5)
        next_run = now + timedelta(seconds=sleep_seconds)
        logger.info(
            "shipment_history scheduler sleeping",
            extra={"next_run": next_run.isoformat()},
        )
        await asyncio.sleep(sleep_seconds)
        try:
            await asyncio.to_thread(refresh_shipment_history_for_all_companies)
        except Exception:
            logger.exception("shipment_history scheduler cycle failed")
