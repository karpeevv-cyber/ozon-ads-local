from __future__ import annotations

from sqlalchemy.orm import Session

from app.db.bootstrap import create_all
from app.db.session import SessionLocal
from app.models.auto_bid_settings import AutoBidCampaignLimit, AutoBidSettings

DEFAULT_MAX_BID_RUB = 25.0


def get_auto_bid_max_bid(company_name: str, db: Session | None = None) -> float:
    create_all()
    owns_session = db is None
    session = db or SessionLocal()
    try:
        row = session.query(AutoBidSettings).filter(AutoBidSettings.company_name == company_name).first()
        return float(row.max_bid_rub) if row is not None else DEFAULT_MAX_BID_RUB
    finally:
        if owns_session:
            session.close()


def save_auto_bid_max_bid(*, company_name: str, max_bid_rub: float, db: Session) -> float:
    create_all()
    row = db.query(AutoBidSettings).filter(AutoBidSettings.company_name == company_name).first()
    if row is None:
        row = AutoBidSettings(company_name=company_name, max_bid_rub=float(max_bid_rub))
        db.add(row)
    else:
        row.max_bid_rub = float(max_bid_rub)
    db.commit()
    db.refresh(row)
    return float(row.max_bid_rub)


def get_campaign_bid_limits(company_name: str, db: Session | None = None) -> dict[tuple[str, str], float]:
    create_all()
    owns_session = db is None
    session = db or SessionLocal()
    try:
        rows = session.query(AutoBidCampaignLimit).filter(AutoBidCampaignLimit.company_name == company_name).all()
        return {(row.campaign_id, row.sku): float(row.max_bid_rub) for row in rows}
    finally:
        if owns_session:
            session.close()


def save_campaign_bid_limit(
    *,
    company_name: str,
    campaign_id: str,
    sku: str,
    max_bid_rub: float,
    db: Session,
    commit: bool = True,
) -> float:
    create_all()
    row = (
        db.query(AutoBidCampaignLimit)
        .filter(
            AutoBidCampaignLimit.company_name == company_name,
            AutoBidCampaignLimit.campaign_id == campaign_id,
            AutoBidCampaignLimit.sku == sku,
        )
        .first()
    )
    if row is None:
        row = AutoBidCampaignLimit(
            company_name=company_name,
            campaign_id=campaign_id,
            sku=sku,
            max_bid_rub=float(max_bid_rub),
        )
        db.add(row)
    else:
        row.max_bid_rub = float(max_bid_rub)
    if commit:
        db.commit()
        db.refresh(row)
    else:
        db.flush()
    return float(row.max_bid_rub)
