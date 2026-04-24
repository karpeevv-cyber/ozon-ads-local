from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class MainOverviewCache(Base):
    __tablename__ = "main_overview_cache"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_name: Mapped[str] = mapped_column(Text, index=True, default="", nullable=False)
    date_from: Mapped[str] = mapped_column(Text, index=True, default="", nullable=False)
    date_to: Mapped[str] = mapped_column(Text, index=True, default="", nullable=False)
    target_drr_pct: Mapped[str] = mapped_column(Text, index=True, default="", nullable=False)
    payload_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
