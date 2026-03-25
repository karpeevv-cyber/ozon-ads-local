from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class TrendsSnapshotResponse(BaseModel):
    niches: list[dict[str, Any]]
    products: list[dict[str, Any]]
    external_sources: list[dict[str, Any]]
    errors: list[str]
    meta: dict[str, Any]
