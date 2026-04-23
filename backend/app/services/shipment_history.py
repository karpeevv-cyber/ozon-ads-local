from __future__ import annotations

from datetime import datetime
from typing import Iterable

from sqlalchemy.orm import Session

from app.db.bootstrap import create_all
from app.services.integrations.ozon_seller import (
    seller_supply_order_bundle_query,
    seller_supply_order_get,
    seller_supply_order_list,
)


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


def _completed_order_ids(
    *,
    seller_client_id: str,
    seller_api_key: str,
    limit: int = 100,
    max_pages: int = 200,
) -> list[str]:
    states = [
        "ACCEPTED_AT_SUPPLY_WAREHOUSE",
        "IN_TRANSIT",
        "ACCEPTANCE_AT_STORAGE_WAREHOUSE",
        "COMPLETED",
    ]
    out: list[str] = []
    last_id = ""
    seen_last: set[str] = set()
    for _ in range(max_pages):
        response = seller_supply_order_list(
            filter={"states": states},
            last_id=last_id,
            limit=limit,
            sort_by="ORDER_CREATION",
            sort_dir="DESC",
            client_id=seller_client_id,
            api_key=seller_api_key,
        )
        order_ids = [str(value) for value in (response.get("order_ids") or []) if str(value).strip()]
        if not order_ids:
            break
        out.extend(order_ids)
        next_last_id = str(response.get("last_id") or "").strip()
        if not next_last_id or next_last_id in seen_last:
            break
        seen_last.add(next_last_id)
        last_id = next_last_id
    return list(dict.fromkeys(out))


def _chunked(values: Iterable[str], size: int) -> Iterable[list[str]]:
    batch: list[str] = []
    for value in values:
        batch.append(value)
        if len(batch) >= size:
            yield batch
            batch = []
    if batch:
        yield batch


def _orders_by_ids(
    *,
    order_ids: list[str],
    seller_client_id: str,
    seller_api_key: str,
) -> list[dict]:
    out: list[dict] = []
    for batch in _chunked(order_ids, 50):
        response = seller_supply_order_get(
            order_ids=batch,
            client_id=seller_client_id,
            api_key=seller_api_key,
        )
        orders = response.get("orders") or []
        for item in orders:
            if isinstance(item, dict):
                out.append(item)
    return out


def _bundle_items(
    *,
    bundle_id: str,
    dropoff_warehouse_id: str,
    storage_warehouse_id: str,
    seller_client_id: str,
    seller_api_key: str,
) -> list[dict]:
    out: list[dict] = []
    last_id = ""
    for _ in range(500):
        response = seller_supply_order_bundle_query(
            bundle_ids=[bundle_id],
            dropoff_warehouse_id=dropoff_warehouse_id,
            storage_warehouse_ids=[storage_warehouse_id],
            limit=100,
            sort_field="NAME",
            is_asc=True,
            last_id=last_id,
            client_id=seller_client_id,
            api_key=seller_api_key,
        )
        items = response.get("items") or []
        for item in items:
            if isinstance(item, dict):
                out.append(item)
        if not bool(response.get("has_next", False)):
            break
        next_last_id = str(response.get("last_id") or "").strip()
        if not next_last_id or next_last_id == last_id:
            break
        last_id = next_last_id
    return out


def rebuild_shipment_history_from_api(
    db: Session,
    *,
    company_name: str,
    seller_client_id: str,
    seller_api_key: str,
) -> int:
    if not seller_client_id or not seller_api_key:
        return 0

    order_ids = _completed_order_ids(
        seller_client_id=seller_client_id,
        seller_api_key=seller_api_key,
    )
    if not order_ids:
        sync_shipment_history(
            db,
            company_name=company_name,
            seller_client_id=seller_client_id,
            lot_rows=[],
        )
        return 0

    orders = _orders_by_ids(
        order_ids=order_ids,
        seller_client_id=seller_client_id,
        seller_api_key=seller_api_key,
    )

    lot_rows: list[dict] = []
    bundle_cache: dict[tuple[str, str, str], list[dict]] = {}
    for order in orders:
        if not isinstance(order, dict):
            continue
        dropoff = order.get("drop_off_warehouse") or {}
        dropoff_id = str(dropoff.get("warehouse_id") or "").strip()
        if not dropoff_id:
            continue
        supplies = order.get("supplies") or []
        for supply in supplies:
            if not isinstance(supply, dict):
                continue
            storage = supply.get("storage_warehouse") or {}
            storage_id = str(storage.get("warehouse_id") or "").strip()
            storage_name = str(storage.get("name") or "").strip()
            bundle_id = str(supply.get("bundle_id") or "").strip()
            if not storage_id or not bundle_id:
                continue
            city = storage_name or storage_id
            city_key = normalize_city(city)
            cache_key = (bundle_id, dropoff_id, storage_id)
            items = bundle_cache.get(cache_key)
            if items is None:
                try:
                    items = _bundle_items(
                        bundle_id=bundle_id,
                        dropoff_warehouse_id=dropoff_id,
                        storage_warehouse_id=storage_id,
                        seller_client_id=seller_client_id,
                        seller_api_key=seller_api_key,
                    )
                except Exception:
                    items = []
                bundle_cache[cache_key] = items
            for item in items:
                article = str(item.get("offer_id") or "").strip()
                if not article:
                    continue
                lot_rows.append(
                    {
                        "article": article,
                        "city_key": city_key,
                        "city": city,
                    }
                )

    sync_shipment_history(
        db,
        company_name=company_name,
        seller_client_id=seller_client_id,
        lot_rows=lot_rows,
    )
    return len(lot_rows)
