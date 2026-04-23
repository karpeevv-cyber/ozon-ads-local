from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ShipmentHistory(Base):
    __tablename__ = "shipment_history"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_name: Mapped[str] = mapped_column(Text, index=True, default="", nullable=False)
    seller_client_id: Mapped[str] = mapped_column(Text, index=True, default="", nullable=False)
    article: Mapped[str] = mapped_column(Text, index=True, default="", nullable=False)
    city_key: Mapped[str] = mapped_column(Text, index=True, default="", nullable=False)
    shipments_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    first_shipment_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    last_shipment_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
