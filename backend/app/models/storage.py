from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class StorageSnapshotCache(Base):
    __tablename__ = "storage_snapshot_cache"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_name: Mapped[str] = mapped_column(Text, index=True, default="", nullable=False)
    seller_client_id: Mapped[str] = mapped_column(Text, index=True, default="", nullable=False)
    version: Mapped[str] = mapped_column(Text, default="v12", nullable=False)
    snapshot_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    source_ref: Mapped[str] = mapped_column(Text, default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
