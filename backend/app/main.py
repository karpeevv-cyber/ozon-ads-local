from fastapi import FastAPI

from app.api.router import build_api_router
from app.core.config import get_settings


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        debug=settings.debug,
    )
    app.include_router(build_api_router(), prefix=settings.api_prefix)
    return app


app = create_app()
