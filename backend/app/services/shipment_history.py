from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from app.db.bootstrap import create_all


def normalize_city(value: str) -> str:
    text = str(value or "").strip().upper().replace("Ё", "Е")
    if not text:
        return "UNKNOWN"
    if "МОСКВА" in text or "МО И ДАЛЬНИЕ РЕГИОНЫ" in text or "МО И ДАЛ" in text:
        return "МОСКВА"
    if "САНКТ-ПЕТЕРБУРГ" in text or "СЗО" in text:
        return "САНКТ-ПЕТЕРБУРГ"
    for prefix in ("ГРИВНО", "НОГИНСК", "ПУШКИНО", "ХОРУГВИНО", "ПЕТРОВСКОЕ"):
        if text.startswith(prefix):
            return "МОСКВА"
    for suffix in ("_РФЦ_НОВЫЙ", "_МРФЦ", "_РФЦ", "_РЦ"):
        if text.endswith(suffix):
            text = text[: -len(suffix)]
            break
    text = text.replace("_1", "").replace("_2", "").strip("_ ").strip()
    return text or "UNKNOWN"


def sync_shipment_history(
    db: Session,
    *,
    company_name: str,
    seller_client_id: str,
    lot_rows: list[dict],
) -> None:
    if not seller_client_id:
        return
    create_all()
    from app.models.shipment_history import ShipmentHistory

    now = datetime.utcnow()
    aggregates: dict[tuple[str, str], int] = {}
    for row in lot_rows:
        if not isinstance(row, dict):
            continue
        article = str(row.get("article") or "").strip()
        if not article:
            continue
        city_key = str(row.get("city_key") or "").strip()
        if not city_key:
            city_key = normalize_city(str(row.get("city") or ""))
        if not city_key:
            continue
        key = (article, city_key)
        aggregates[key] = aggregates.get(key, 0) + 1

    (
        db.query(ShipmentHistory)
        .filter(ShipmentHistory.company_name == str(company_name or ""))
        .filter(ShipmentHistory.seller_client_id == str(seller_client_id or ""))
        .delete(synchronize_session=False)
    )

    if aggregates:
        rows = [
            ShipmentHistory(
                company_name=str(company_name or ""),
                seller_client_id=str(seller_client_id or ""),
                article=article,
                city_key=city_key,
                shipments_count=int(count),
                first_shipment_at=now,
                last_shipment_at=now,
            )
            for (article, city_key), count in aggregates.items()
        ]
        db.bulk_save_objects(rows)
    db.commit()


def load_shipment_pairs(
    db: Session,
    *,
    company_name: str,
    seller_client_id: str,
) -> tuple[set[tuple[str, str]], datetime | None]:
    if not seller_client_id:
        return set(), None
    create_all()
    from app.models.shipment_history import ShipmentHistory

    rows = (
        db.query(ShipmentHistory)
        .filter(ShipmentHistory.company_name == str(company_name or ""))
        .filter(ShipmentHistory.seller_client_id == str(seller_client_id or ""))
        .filter(ShipmentHistory.shipments_count > 0)
        .all()
    )
    if not rows:
        return set(), None
    pairs = {
        (str(item.article or "").strip(), str(item.city_key or "").strip())
        for item in rows
        if str(item.article or "").strip() and str(item.city_key or "").strip()
    }
    ts = max((item.updated_at for item in rows if item.updated_at is not None), default=None)
    return pairs, ts
