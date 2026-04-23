from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.router import build_api_router
from app.core.config import get_settings
from app.services.shipment_history_scheduler import shipment_history_scheduler_loop

logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    settings = get_settings()

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        scheduler_task = asyncio.create_task(
            shipment_history_scheduler_loop(settings.timezone),
            name="shipment-history-daily-scheduler",
        )
        try:
            yield
        finally:
            scheduler_task.cancel()
            try:
                await scheduler_task
            except asyncio.CancelledError:
                logger.info("shipment_history scheduler stopped")

    app = FastAPI(
        title=settings.app_name,
        debug=settings.debug,
        lifespan=lifespan,
    )
    app.include_router(build_api_router(), prefix=settings.api_prefix)
    return app


app = create_app()
