from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.router import build_api_router
from app.core.config import get_settings
from app.services.auto_bids import auto_bids_scheduler_loop
from app.services.campaign_hourly import campaign_hourly_scheduler_loop
from app.services.finance_telegram import finance_telegram_scheduler_loop
from app.services.shipment_history_scheduler import shipment_history_scheduler_loop

logger = logging.getLogger("uvicorn.error")


def create_app() -> FastAPI:
    settings = get_settings()

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        scheduler_task = asyncio.create_task(
            shipment_history_scheduler_loop(settings.timezone),
            name="shipment-history-daily-scheduler",
        )
        finance_telegram_task = asyncio.create_task(
            finance_telegram_scheduler_loop(settings.timezone),
            name="finance-telegram-daily-scheduler",
        )
        auto_bids_task = asyncio.create_task(
            auto_bids_scheduler_loop(settings.timezone),
            name="auto-bids-daily-scheduler",
        )
        campaign_hourly_task = asyncio.create_task(
            campaign_hourly_scheduler_loop(settings.timezone),
            name="campaign-hourly-scheduler",
        )
        try:
            yield
        finally:
            for task, task_name in [
                (scheduler_task, "shipment_history scheduler"),
                (finance_telegram_task, "finance telegram scheduler"),
                (auto_bids_task, "auto bids scheduler"),
                (campaign_hourly_task, "campaign hourly scheduler"),
            ]:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    logger.info("%s stopped", task_name)

    app = FastAPI(
        title=settings.app_name,
        debug=settings.debug,
        lifespan=lifespan,
    )
    app.include_router(build_api_router(), prefix=settings.api_prefix)
    return app


app = create_app()
