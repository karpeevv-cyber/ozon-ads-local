from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Date, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Campaign(Base):
    __tablename__ = "campaigns"

    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    external_campaign_id: Mapped[str] = mapped_column(String(128), index=True)
    title: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    state: Mapped[str] = mapped_column(String(128), default="", nullable=False)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    products: Mapped[list["CampaignProduct"]] = relationship(back_populates="campaign")
    daily_metrics: Mapped[list["CampaignDailyMetric"]] = relationship(back_populates="campaign")


class CampaignProduct(Base):
    __tablename__ = "campaign_products"

    id: Mapped[int] = mapped_column(primary_key=True)
    campaign_id: Mapped[int] = mapped_column(ForeignKey("campaigns.id"), index=True)
    sku: Mapped[str] = mapped_column(String(128), index=True)
    title: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    current_bid_micro: Mapped[int | None] = mapped_column(Integer, nullable=True)
    raw_payload_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    campaign: Mapped["Campaign"] = relationship(back_populates="products")


class CampaignDailyMetric(Base):
    __tablename__ = "campaign_daily_metrics"

    id: Mapped[int] = mapped_column(primary_key=True)
    campaign_id: Mapped[int] = mapped_column(ForeignKey("campaigns.id"), index=True)
    day: Mapped[date] = mapped_column(Date, index=True)
    views: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    clicks: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    money_spent: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    click_price: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    orders: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    orders_money_ads: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    total_revenue: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    ordered_units: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_drr_pct: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    raw_ads_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    raw_seller_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    campaign: Mapped["Campaign"] = relationship(back_populates="daily_metrics")
