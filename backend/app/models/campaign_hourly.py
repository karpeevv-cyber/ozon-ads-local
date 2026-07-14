from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Date, DateTime, Float, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class CampaignHourlySnapshot(Base):
    __tablename__ = "campaign_hourly_snapshots"
    __table_args__ = (
        UniqueConstraint("company", "campaign_id", "day", "sample_hour", name="uq_campaign_hourly_sample"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    company: Mapped[str] = mapped_column(String(128), index=True)
    campaign_id: Mapped[str] = mapped_column(String(128), index=True)
    campaign_title: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    day: Mapped[date] = mapped_column(Date, index=True)
    sample_hour: Mapped[int] = mapped_column(Integer, index=True)
    sample_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    views: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    clicks: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    money_spent: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    raw_ads_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
