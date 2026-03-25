from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Organization(Base):
    __tablename__ = "organizations"

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255), unique=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    credentials: Mapped[list["MarketplaceCredential"]] = relationship(back_populates="organization")
    memberships: Mapped[list["OrganizationMembership"]] = relationship(back_populates="organization")


class MarketplaceCredential(Base):
    __tablename__ = "marketplace_credentials"

    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    provider: Mapped[str] = mapped_column(String(64), default="ozon", nullable=False)
    perf_client_id: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    perf_client_secret: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    seller_client_id: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    seller_api_key: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    organization: Mapped["Organization"] = relationship(back_populates="credentials")
