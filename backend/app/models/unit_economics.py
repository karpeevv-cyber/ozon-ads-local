from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class UnitEconomicsOverride(Base):
    __tablename__ = "unit_economics_overrides"
    __table_args__ = (
        UniqueConstraint("company_name", "seller_client_id", "sku", name="uq_unit_economics_override_scope"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    company_name: Mapped[str] = mapped_column(String(255), index=True, default="", nullable=False)
    seller_client_id: Mapped[str] = mapped_column(String(255), index=True, default="", nullable=False)
    sku: Mapped[str] = mapped_column(String(128), index=True)
    position: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    tea_cost: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    package_cost: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    label_cost: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    packing_cost: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
