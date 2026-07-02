from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from app.db.bootstrap import create_all
from app.models.stock_warehouse_preference import StockWarehousePreference


def load_stock_warehouse_preferences(
    db: Session | None,
    *,
    company_name: str,
    seller_client_id: str,
) -> dict[str, bool]:
    if db is None:
        return {}
    create_all()
    rows = (
        db.query(StockWarehousePreference)
        .filter(StockWarehousePreference.company_name == company_name)
        .filter(StockWarehousePreference.seller_client_id == seller_client_id)
        .all()
    )
    return {str(row.city_key or "").strip(): bool(row.is_used_for_shipments) for row in rows if str(row.city_key or "").strip()}


def save_stock_warehouse_preferences(
    db: Session,
    *,
    company_name: str,
    seller_client_id: str,
    city_keys: list[str],
    city_labels: dict[str, str] | None = None,
) -> dict[str, bool]:
    create_all()
    normalized_keys = {str(city_key or "").strip() for city_key in city_keys if str(city_key or "").strip()}
    labels = city_labels or {}
    existing_rows = (
        db.query(StockWarehousePreference)
        .filter(StockWarehousePreference.company_name == company_name)
        .filter(StockWarehousePreference.seller_client_id == seller_client_id)
        .all()
    )
    existing_by_key = {str(row.city_key or "").strip(): row for row in existing_rows if str(row.city_key or "").strip()}
    now = datetime.utcnow()

    for city_key, row in existing_by_key.items():
        row.is_used_for_shipments = city_key in normalized_keys
        row.city_label = labels.get(city_key, row.city_label or city_key)
        row.updated_at = now

    for city_key in normalized_keys - set(existing_by_key):
        db.add(
            StockWarehousePreference(
                company_name=company_name,
                seller_client_id=seller_client_id,
                city_key=city_key,
                city_label=labels.get(city_key, city_key),
                is_used_for_shipments=True,
                created_at=now,
                updated_at=now,
            )
        )

    db.commit()
    return load_stock_warehouse_preferences(db, company_name=company_name, seller_client_id=seller_client_id)
