from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable

from sqlalchemy.orm import Session

from app.db.bootstrap import create_all
from app.services.integrations.ozon_seller import (
    seller_analytics_stocks,
    seller_supply_order_bundle_query,
    seller_supply_order_get,
    seller_supply_order_list,
)

SUPPLY_ORDER_STATES = [
    "DATA_FILLING",
    "READY_TO_SUPPLY",
    "ACCEPTED_AT_SUPPLY_WAREHOUSE",
    "IN_TRANSIT",
    "ACCEPTANCE_AT_STORAGE_WAREHOUSE",
    "REPORTS_CONFIRMATION_AWAITING",
    "REPORT_REJECTED",
    "COMPLETED",
    "REJECTED_AT_SUPPLY_WAREHOUSE",
    "CANCELLED",
    "OVERDUE",
]

ACTIVE_SUPPLY_ORDER_STATES = {
    "READY_TO_SUPPLY",
    "ACCEPTED_AT_SUPPLY_WAREHOUSE",
    "IN_TRANSIT",
    "ACCEPTANCE_AT_STORAGE_WAREHOUSE",
}

MACROLOCAL_CLUSTER_CITY_FALLBACKS = {
    "4039": "МОСКВА",
    "4040": "УФА",
    "4071": "РОСТОВ",
}


def normalize_city(value: str) -> str:
    text = str(value or "").strip().upper().replace("Ё", "Е")
    if not text:
        return "UNKNOWN"
    compact = text.replace(" ", "").replace("-", "").replace("_", "")
    if (
        compact.startswith("СПБ")
        or compact.startswith("SPB")
        or "САНКТПЕТЕРБУРГ" in compact
        or "SAINTPETERSBURG" in compact
        or "STPETERSBURG" in compact
    ):
        return "САНКТ-ПЕТЕРБУРГ"
    if "МОСКВА" in text or "МО И ДАЛЬНИЕ РЕГИОНЫ" in text or "МО И ДАЛ" in text:
        return "МОСКВА"
    if "САНКТ-ПЕТЕРБУРГ" in text or "СЗО" in text:
        return "САНКТ-ПЕТЕРБУРГ"
    if "ХАБАРОВСК" in text:
        return "ДАЛЬНИЙ"
    if text == "ДАЛЬНИЙ" or "ДАЛЬНИЙ ВОСТОК" in text:
        return "ДАЛЬНИЙ"
    if text == "РОСТОВ":
        return "РОСТОВ"
    if "РОСТОВ-НА-ДОНУ" in text or "ROSTOVONDON" in compact:
        return "РОСТОВ"
    for prefix in ("ГРИВНО", "НОГИНСК", "ПУШКИНО", "ХОРУГВИНО", "ПЕТРОВСКОЕ"):
        if text.startswith(prefix):
            return "МОСКВА"
    for suffix in ("_РФЦ_НОВЫЙ", "_МРФЦ", "_РФЦ", "_РЦ"):
        if text.endswith(suffix):
            text = text[: -len(suffix)]
            break
    text = text.replace("_1", "").replace("_2", "").strip("_ ").strip()
    return text or "UNKNOWN"


def _parse_dt(value: object) -> datetime | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    try:
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is not None:
            dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
        return dt
    except Exception:
        return None


def _to_int(value: object) -> int:
    try:
        return int(float(value or 0))
    except Exception:
        return 0


def _event_time(order: dict, supply: dict) -> datetime:
    state = str(order.get("state") or "").strip().upper()
    if state == "COMPLETED":
        completed_at = _parse_dt(order.get("state_updated_date"))
        if completed_at is not None:
            return completed_at

    timeslot = order.get("timeslot") or {}
    nested = timeslot.get("timeslot") or {}
    for key in ("from", "to"):
        dt = _parse_dt(nested.get(key))
        if dt is not None:
            return dt
    for key in (
        "created_date",
        "state_updated_date",
        "updated_at",
        "created_at",
    ):
        dt = _parse_dt(order.get(key))
        if dt is not None:
            return dt
    for key in ("updated_at", "created_at", "date"):
        dt = _parse_dt(supply.get(key))
        if dt is not None:
            return dt
    return datetime.utcnow()


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


def _sync_shipment_events(
    db: Session,
    *,
    company_name: str,
    seller_client_id: str,
    events: list[dict],
) -> None:
    from app.models.shipment_event import ShipmentEvent

    (
        db.query(ShipmentEvent)
        .filter(ShipmentEvent.company_name == str(company_name or ""))
        .filter(ShipmentEvent.seller_client_id == str(seller_client_id or ""))
        .delete(synchronize_session=False)
    )

    if events:
        db.bulk_save_objects(
            [
                ShipmentEvent(
                    company_name=str(company_name or ""),
                    seller_client_id=str(seller_client_id or ""),
                    article=str(item.get("article") or "").strip(),
                    city_key=str(item.get("city_key") or "").strip(),
                    city=str(item.get("city") or "").strip(),
                    event_at=item.get("event_at") or datetime.utcnow(),
                    quantity=max(0, _to_int(item.get("quantity") or 0)),
                    order_id=str(item.get("order_id") or "").strip(),
                    bundle_id=str(item.get("bundle_id") or "").strip(),
                )
                for item in events
                if str(item.get("article") or "").strip() and str(item.get("city_key") or "").strip()
            ]
        )


def _sync_shipment_transit(
    db: Session,
    *,
    company_name: str,
    seller_client_id: str,
    rows: list[dict],
) -> None:
    from app.models.shipment_transit import ShipmentTransit

    (
        db.query(ShipmentTransit)
        .filter(ShipmentTransit.company_name == str(company_name or ""))
        .filter(ShipmentTransit.seller_client_id == str(seller_client_id or ""))
        .delete(synchronize_session=False)
    )

    if rows:
        db.bulk_save_objects(
            [
                ShipmentTransit(
                    company_name=str(company_name or ""),
                    seller_client_id=str(seller_client_id or ""),
                    article=str(item.get("article") or "").strip(),
                    city_key=str(item.get("city_key") or "").strip(),
                    city=str(item.get("city") or "").strip(),
                    quantity=max(0, _to_int(item.get("quantity") or 0)),
                    order_id=str(item.get("order_id") or "").strip(),
                    supply_id=str(item.get("supply_id") or "").strip(),
                    bundle_id=str(item.get("bundle_id") or "").strip(),
                )
                for item in rows
                if str(item.get("article") or "").strip() and str(item.get("city_key") or "").strip()
            ]
        )


def _sync_shipment_history_from_events(
    db: Session,
    *,
    company_name: str,
    seller_client_id: str,
    events: list[dict],
) -> None:
    from app.models.shipment_history import ShipmentHistory

    (
        db.query(ShipmentHistory)
        .filter(ShipmentHistory.company_name == str(company_name or ""))
        .filter(ShipmentHistory.seller_client_id == str(seller_client_id or ""))
        .delete(synchronize_session=False)
    )

    aggregate: dict[tuple[str, str], dict] = {}
    for event in events:
        article = str(event.get("article") or "").strip()
        city_key = str(event.get("city_key") or "").strip()
        event_at = event.get("event_at") or datetime.utcnow()
        if not article or not city_key:
            continue
        key = (article, city_key)
        item = aggregate.get(key)
        if item is None:
            aggregate[key] = {
                "count": 1,
                "first": event_at,
                "last": event_at,
            }
            continue
        item["count"] += 1
        if event_at < item["first"]:
            item["first"] = event_at
        if event_at > item["last"]:
            item["last"] = event_at

    if aggregate:
        db.bulk_save_objects(
            [
                ShipmentHistory(
                    company_name=str(company_name or ""),
                    seller_client_id=str(seller_client_id or ""),
                    article=article,
                    city_key=city_key,
                    shipments_count=int(values["count"]),
                    first_shipment_at=values["first"],
                    last_shipment_at=values["last"],
                )
                for (article, city_key), values in aggregate.items()
            ]
        )


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


def load_shipment_events_map(
    db: Session,
    *,
    company_name: str,
    seller_client_id: str,
    articles: set[str],
    city_keys: set[str],
    per_cell_limit: int = 5,
) -> dict[tuple[str, str], dict]:
    if not seller_client_id or not articles or not city_keys:
        return {}
    create_all()
    from app.models.shipment_event import ShipmentEvent

    rows = (
        db.query(ShipmentEvent)
        .filter(ShipmentEvent.company_name == str(company_name or ""))
        .filter(ShipmentEvent.seller_client_id == str(seller_client_id or ""))
        .filter(ShipmentEvent.article.in_(sorted(articles)))
        .filter(ShipmentEvent.city_key.in_(sorted(city_keys)))
        .order_by(ShipmentEvent.event_at.desc())
        .all()
    )
    out: dict[tuple[str, str], dict] = {}
    for item in rows:
        article = str(item.article or "").strip()
        city_key = str(item.city_key or "").strip()
        if not article or not city_key:
            continue
        key = (article, city_key)
        entry = out.get(key)
        if entry is None:
            entry = {
                "total_quantity": 0,
                "events_count": 0,
                "last_event_at": None,
                "events": [],
                "events_for_calc": [],
            }
            out[key] = entry
        qty = int(item.quantity or 0)
        entry["total_quantity"] += qty
        entry["events_count"] += 1
        if entry["last_event_at"] is None:
            entry["last_event_at"] = item.event_at
        entry["events_for_calc"].append(
            {
                "quantity": qty,
                "event_at": item.event_at,
            }
        )
        if len(entry["events"]) < max(1, int(per_cell_limit)):
            entry["events"].append(
                {
                    "quantity": qty,
                    "event_at": item.event_at,
                    "city": str(item.city or "").strip(),
                }
            )
    return out


def load_shipment_transit_map(
    db: Session,
    *,
    company_name: str,
    seller_client_id: str,
    articles: set[str],
    city_keys: set[str] | None = None,
) -> dict[tuple[str, str], int]:
    if db is None or not seller_client_id or not articles:
        return {}
    create_all()
    from app.models.shipment_transit import ShipmentTransit

    query = (
        db.query(ShipmentTransit)
        .filter(ShipmentTransit.company_name == str(company_name or ""))
        .filter(ShipmentTransit.seller_client_id == str(seller_client_id or ""))
        .filter(ShipmentTransit.article.in_(sorted(articles)))
    )
    if city_keys:
        query = query.filter(ShipmentTransit.city_key.in_(sorted(city_keys)))
    rows = query.all()
    out: dict[tuple[str, str], int] = {}
    for item in rows:
        article = str(item.article or "").strip()
        city_key = str(item.city_key or "").strip()
        if not article or not city_key:
            continue
        key = (article, city_key)
        out[key] = out.get(key, 0) + int(item.quantity or 0)
    return out


def _completed_order_ids(
    *,
    seller_client_id: str,
    seller_api_key: str,
    limit: int = 100,
    max_pages: int = 200,
) -> list[str]:
    out: list[str] = []
    last_id = ""
    seen_last: set[str] = set()
    for _ in range(max_pages):
        response = seller_supply_order_list(
            filter={"states": SUPPLY_ORDER_STATES},
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
        try:
            response = seller_supply_order_get(
                order_ids=batch,
                client_id=seller_client_id,
                api_key=seller_api_key,
            )
        except Exception:
            response = {"orders": []}
            for order_id in batch:
                try:
                    single_response = seller_supply_order_get(
                        order_ids=[order_id],
                        client_id=seller_client_id,
                        api_key=seller_api_key,
                    )
                except Exception:
                    continue
                response["orders"].extend(single_response.get("orders") or [])
        orders = response.get("orders") or []
        for item in orders:
            if isinstance(item, dict):
                out.append(item)
    return out


def _bundle_items(
    *,
    bundle_id: str,
    dropoff_warehouse_id: str,
    storage_warehouse_id: str = "",
    seller_client_id: str,
    seller_api_key: str,
) -> list[dict]:
    out: list[dict] = []
    last_id = ""
    for _ in range(500):
        response = seller_supply_order_bundle_query(
            bundle_ids=[bundle_id],
            dropoff_warehouse_id=dropoff_warehouse_id,
            storage_warehouse_ids=[storage_warehouse_id] if storage_warehouse_id else [],
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


def _city_from_macrolocal_cluster(
    *,
    macrolocal_cluster_id: str,
    items: list[dict],
    seller_client_id: str,
    seller_api_key: str,
) -> str:
    cluster_id = str(macrolocal_cluster_id or "").strip()
    if not cluster_id:
        return "UNKNOWN"

    sku = ""
    for item in items:
        sku_value = item.get("sku") if isinstance(item, dict) else None
        if str(sku_value or "").strip().isdigit():
            sku = str(sku_value).strip()
            break

    if sku:
        try:
            response = seller_analytics_stocks(
                skus=[sku],
                cluster_ids=[int(cluster_id)],
                client_id=seller_client_id,
                api_key=seller_api_key,
            )
            for row in response.get("items", []) or []:
                if str(row.get("macrolocal_cluster_id") or "").strip() == cluster_id:
                    city = normalize_city(str(row.get("cluster_name") or ""))
                    if city and city != "UNKNOWN":
                        return city
        except Exception:
            pass

    return MACROLOCAL_CLUSTER_CITY_FALLBACKS.get(cluster_id, "UNKNOWN")


def rebuild_shipment_history_from_api(
    db: Session,
    *,
    company_name: str,
    seller_client_id: str,
    seller_api_key: str,
) -> int:
    if not seller_client_id or not seller_api_key:
        return 0

    create_all()
    order_ids = _completed_order_ids(
        seller_client_id=seller_client_id,
        seller_api_key=seller_api_key,
    )
    if not order_ids:
        _sync_shipment_events(
            db,
            company_name=company_name,
            seller_client_id=seller_client_id,
            events=[],
        )
        _sync_shipment_transit(
            db,
            company_name=company_name,
            seller_client_id=seller_client_id,
            rows=[],
        )
        _sync_shipment_history_from_events(
            db,
            company_name=company_name,
            seller_client_id=seller_client_id,
            events=[],
        )
        db.commit()
        return 0

    orders = _orders_by_ids(
        order_ids=order_ids,
        seller_client_id=seller_client_id,
        seller_api_key=seller_api_key,
    )

    events: list[dict] = []
    transit_rows: list[dict] = []
    bundle_cache: dict[tuple[str, str, str], list[dict]] = {}
    for order in orders:
        if not isinstance(order, dict):
            continue
        order_id = str(order.get("order_id") or "").strip()
        order_state = str(order.get("state") or "").strip().upper()
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
            supply_id = str(supply.get("supply_id") or "").strip()
            macrolocal_cluster_id = str(supply.get("macrolocal_cluster_id") or "").strip()
            if not bundle_id:
                continue
            event_at = _event_time(order, supply)
            cache_key = (bundle_id, dropoff_id, storage_id or macrolocal_cluster_id)
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
            if storage_id:
                city = storage_name or storage_id
                city_key = normalize_city(city)
            else:
                city_key = _city_from_macrolocal_cluster(
                    macrolocal_cluster_id=macrolocal_cluster_id,
                    items=items,
                    seller_client_id=seller_client_id,
                    seller_api_key=seller_api_key,
                )
                city = city_key
            for item in items:
                article = str(item.get("offer_id") or "").strip()
                if not article:
                    continue
                quantity = max(
                    _to_int(item.get("quantity")),
                    _to_int(item.get("qty")),
                    _to_int(item.get("count")),
                    1,
                )
                events.append(
                    {
                        "article": article,
                        "city_key": city_key,
                        "city": city,
                        "event_at": event_at,
                        "quantity": quantity,
                        "order_id": order_id,
                        "bundle_id": bundle_id,
                    }
                )
                if order_state in ACTIVE_SUPPLY_ORDER_STATES:
                    transit_rows.append(
                        {
                            "article": article,
                            "city_key": city_key,
                            "city": city,
                            "quantity": quantity,
                            "order_id": order_id,
                            "supply_id": supply_id,
                            "bundle_id": bundle_id,
                        }
                    )

    _sync_shipment_events(
        db,
        company_name=company_name,
        seller_client_id=seller_client_id,
        events=events,
    )
    _sync_shipment_transit(
        db,
        company_name=company_name,
        seller_client_id=seller_client_id,
        rows=transit_rows,
    )
    _sync_shipment_history_from_events(
        db,
        company_name=company_name,
        seller_client_id=seller_client_id,
        events=events,
    )
    db.commit()
    return len(events)
