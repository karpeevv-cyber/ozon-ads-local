from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ShipmentEvent(Base):
    __tablename__ = "shipment_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_name: Mapped[str] = mapped_column(Text, index=True, default="", nullable=False)
    seller_client_id: Mapped[str] = mapped_column(Text, index=True, default="", nullable=False)
    article: Mapped[str] = mapped_column(Text, index=True, default="", nullable=False)
    city_key: Mapped[str] = mapped_column(Text, index=True, default="", nullable=False)
    city: Mapped[str] = mapped_column(Text, default="", nullable=False)
    event_at: Mapped[datetime] = mapped_column(DateTime, index=True, default=datetime.utcnow, nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    order_id: Mapped[str] = mapped_column(Text, index=True, default="", nullable=False)
    bundle_id: Mapped[str] = mapped_column(Text, index=True, default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
