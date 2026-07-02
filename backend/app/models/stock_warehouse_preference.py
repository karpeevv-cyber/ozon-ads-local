from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class StockWarehousePreference(Base):
    __tablename__ = "stock_warehouse_preferences"
    __table_args__ = (
        UniqueConstraint(
            "company_name",
            "seller_client_id",
            "city_key",
            name="uq_stock_warehouse_preference_scope",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    company_name: Mapped[str] = mapped_column(String(255), index=True, default="", nullable=False)
    seller_client_id: Mapped[str] = mapped_column(String(255), index=True, default="", nullable=False)
    city_key: Mapped[str] = mapped_column(String(255), index=True, default="", nullable=False)
    city_label: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    is_used_for_shipments: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
