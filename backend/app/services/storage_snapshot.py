from __future__ import annotations

import json
import shutil
import sys
import types
from datetime import datetime, timedelta

import pandas as pd
from sqlalchemy.orm import Session

from app.db.bootstrap import create_all
from app.services.company_config import resolve_company_config
from app.services.legacy_compat import build_fee_risk_forecast_table, load_storage_cache_payload
from app.services.shipment_history import sync_shipment_history
from app.services.storage_paths import REPO_ROOT, backend_data_path


def _install_streamlit_stub() -> None:
    if "streamlit" in sys.modules:
        return
    stub = types.ModuleType("streamlit")
    stub.session_state = {}
    stub.cache_data = lambda *args, **kwargs: (lambda fn: fn)
    sys.modules["streamlit"] = stub


def _rebuild_storage_payload_from_api(
    *,
    seller_client_id: str,
    seller_api_key: str,
    cache_version: str,
) -> tuple[dict, datetime]:
    # Reuse the legacy Storage domain logic without importing Streamlit UI runtime.
    _install_streamlit_stub()
    import pickle
    import ui_storage_tab as legacy_storage

    stock_map, sku_count, stock_city_labels, sales_rate_map = legacy_storage._load_stock_by_city_article(
        seller_client_id=seller_client_id,
        seller_api_key=seller_api_key,
    )
    order_ids = legacy_storage._load_completed_order_ids(
        seller_client_id=seller_client_id,
        seller_api_key=seller_api_key,
    )
    orders_by_id = legacy_storage._load_orders_by_id(
        order_ids=order_ids,
        seller_client_id=seller_client_id,
        seller_api_key=seller_api_key,
    )
    lots_map = legacy_storage._build_lots_by_city_article(
        orders_by_id=orders_by_id,
        seller_client_id=seller_client_id,
        seller_api_key=seller_api_key,
    )
    now = datetime.now()
    stock_city_keys = set(stock_city_labels.keys())
    article_volume_map = legacy_storage._item_volume_liters_map_for_store(seller_client_id)
    stock_by_city_article: dict[tuple[str, str], float] = {}
    for (city, article), qty in stock_map.items():
        key = (str(city), str(article))
        stock_by_city_article[key] = stock_by_city_article.get(key, 0.0) + legacy_storage._to_float(qty)

    all_lots: list[dict] = []
    for lots in lots_map.values():
        all_lots.extend(lots)

    lots_by_city_article_flat: dict[tuple[str, str], list[dict]] = {}
    for lot in all_lots:
        city = legacy_storage._map_warehouse_city_to_stock_key(str(lot.get("city", "")), stock_city_keys)
        article = str(lot.get("article", ""))
        if not article:
            continue
        lot["_mapped_city_key"] = city
        lots_by_city_article_flat.setdefault((city, article), []).append(lot)
    for key in lots_by_city_article_flat:
        lots_by_city_article_flat[key].sort(key=lambda item: item["arrival_dt"])

    remaining_map: dict[tuple[str, str, str, str, str], float] = {}
    unknown_stock_rows: list[dict] = []
    for (city_key, article), rows in lots_by_city_article_flat.items():
        current_stock = max(0.0, legacy_storage._to_float(stock_by_city_article.get((city_key, article), 0.0)))
        need = current_stock
        for lot in reversed(rows):
            if need <= 0:
                break
            lot_qty = max(0.0, legacy_storage._to_float(lot.get("qty", 0)))
            take = min(lot_qty, need)
            if take <= 0:
                continue
            map_key = (
                str(city_key),
                str(lot.get("article", "")),
                str(lot.get("order_id", "")),
                str(lot.get("bundle_id", "")),
                lot["arrival_dt"].date().isoformat(),
            )
            remaining_map[map_key] = remaining_map.get(map_key, 0.0) + take
            need -= take
        if need > 0:
            unknown_stock_rows.append(
                {
                    "city": stock_city_labels.get(city_key, city_key),
                    "article": article,
                    "unknown_qty_not_matched_to_shipments": int(round(need)),
                }
            )

    lot_rows: list[dict] = []
    for lot in all_lots:
        article = str(lot.get("article", ""))
        if not article:
            continue
        arrival_date = lot["arrival_dt"].date().isoformat()
        fee_from_dt = lot["arrival_dt"] + timedelta(days=120)
        mapped_city_key = str(lot.get("_mapped_city_key", legacy_storage._norm_city(str(lot.get("city", "")))))
        map_key = (
            mapped_city_key,
            article,
            str(lot.get("order_id", "")),
            str(lot.get("bundle_id", "")),
            arrival_date,
        )
        qty_remaining = int(round(remaining_map.get(map_key, 0.0)))
        lot_rows.append(
            {
                "city": stock_city_labels.get(mapped_city_key, mapped_city_key),
                "shipment_city": str(lot.get("city", "")),
                "storage_warehouse_name": str(lot.get("storage_warehouse_name", "")),
                "storage_warehouse_id": str(lot.get("storage_warehouse_id", "")),
                "article": article,
                "item_volume_liters": article_volume_map.get(article),
                "city_key": mapped_city_key,
                "sales_per_day": round(legacy_storage._to_float(sales_rate_map.get((mapped_city_key, article), 0.0)), 6),
                "shipped_qty": int(round(legacy_storage._to_float(lot.get("qty", 0)))),
                "qty_remaining_from_lot": qty_remaining,
                "in_current_stock": bool(qty_remaining > 0),
                "arrival_date": arrival_date,
                "fee_from_date": fee_from_dt.date().isoformat(),
                "days_until_fee_start": int(max(0, (fee_from_dt.date() - now.date()).days)),
                "fee_started": int(max(0, (fee_from_dt.date() - now.date()).days)) == 0,
                "order_id": str(lot.get("order_id", "")),
                "order_number": str(lot.get("order_number", "")),
                "bundle_id": str(lot.get("bundle_id", "")),
            }
        )
    for row in lot_rows:
        volume = legacy_storage._to_float(row.get("item_volume_liters"))
        qty_remaining = legacy_storage._to_float(row.get("qty_remaining_from_lot"))
        row["daily_storage_fee_rub"] = round(volume * qty_remaining * 2.5, 2) if bool(row.get("fee_started")) else 0.0
        row["projected_storage_fee_rub"] = round(volume * qty_remaining * 2.5, 2)

    payload = {
        "lot_rows": lot_rows,
        "unknown_stock_rows": unknown_stock_rows,
        "sku_count": sku_count,
        "order_count": len(order_ids),
        "ship_lot_count": len(all_lots),
        "stock_articles_count": len(stock_by_city_article),
    }
    cache_path = backend_data_path(f"storage_cache_{cache_version}_{seller_client_id}.pkl")
    with open(cache_path, "wb") as file:
        pickle.dump({"data": payload, "ts": now}, file)
    return payload, now


def _load_storage_snapshot_from_db(
    db: Session,
    *,
    company_name: str,
    seller_client_id: str,
    version: str,
) -> tuple[dict, str, str | None]:
    create_all()
    from app.models.storage import StorageSnapshotCache

    row = (
        db.query(StorageSnapshotCache)
        .filter(StorageSnapshotCache.company_name == str(company_name or ""))
        .filter(StorageSnapshotCache.seller_client_id == str(seller_client_id or ""))
        .filter(StorageSnapshotCache.version == str(version))
        .order_by(StorageSnapshotCache.updated_at.desc())
        .first()
    )
    if row is None:
        return {}, "", None
    try:
        return json.loads(row.snapshot_json), str(row.source_ref or ""), row.updated_at.isoformat() if row.updated_at else None
    except Exception:
        return {}, "", None


def _save_storage_snapshot_to_db(
    db: Session,
    *,
    company_name: str,
    seller_client_id: str,
    version: str,
    payload: dict,
    source_ref: str,
) -> None:
    create_all()
    from app.models.storage import StorageSnapshotCache

    row = (
        db.query(StorageSnapshotCache)
        .filter(StorageSnapshotCache.company_name == str(company_name or ""))
        .filter(StorageSnapshotCache.seller_client_id == str(seller_client_id or ""))
        .filter(StorageSnapshotCache.version == str(version))
        .first()
    )
    if row is None:
        row = StorageSnapshotCache(
            company_name=str(company_name or ""),
            seller_client_id=str(seller_client_id or ""),
            version=str(version),
        )
        db.add(row)
    row.snapshot_json = json.dumps(payload or {}, ensure_ascii=False)
    row.source_ref = str(source_ref or "")
    db.commit()


def _backend_storage_cache_path(seller_client_id: str, version: str) -> str:
    return str(backend_data_path(f"storage_cache_{version}_{seller_client_id}.pkl"))


def _ensure_backend_storage_cache_file(
    *,
    seller_client_id: str,
    version: str,
    payload: dict,
    source_ref: str,
) -> str:
    target_path = _backend_storage_cache_path(seller_client_id, version)
    if not payload:
        return source_ref
    if source_ref == target_path:
        return source_ref
    try:
        source_path = source_ref.strip()
        if source_path and source_path != target_path and pd.notna(source_path):
            source_obj_path = REPO_ROOT / source_path if not str(source_path).startswith(("\\", "/")) and ":" not in str(source_path) else source_path
            source_obj = shutil.copy2(str(source_obj_path), target_path)
            return str(source_obj)
    except Exception:
        pass
    try:
        import pickle
        from datetime import datetime

        with open(target_path, "wb") as file:
            pickle.dump({"data": payload, "ts": datetime.now()}, file)
        return target_path
    except Exception:
        return source_ref


def get_storage_snapshot(*, company: str | None = None, force_refresh: bool = False, db: Session | None = None) -> dict:
    company_name, config = resolve_company_config(company)
    seller_client_id = (config.get("seller_client_id") or "").strip()
    cache_version = "v12"

    if not seller_client_id:
        return {
            "company": company_name,
            "seller_client_id": seller_client_id,
            "cache_updated_at": None,
            "cache_source": "",
            "lot_rows": [],
            "risk_rows": [],
            "unknown_stock_rows": [],
            "sku_count": 0,
            "order_count": 0,
            "ship_lot_count": 0,
            "stock_articles_count": 0,
        }

    payload: dict = {}
    source_ref = ""
    cache_updated_at: str | None = None
    if force_refresh:
        payload, rebuilt_at = _rebuild_storage_payload_from_api(
            seller_client_id=seller_client_id,
            seller_api_key=(config.get("seller_api_key") or "").strip(),
            cache_version=cache_version,
        )
        cache_updated_at = rebuilt_at.isoformat()
        source_ref = _backend_storage_cache_path(seller_client_id, cache_version)
        if db is not None and payload:
            _save_storage_snapshot_to_db(
                db,
                company_name=company_name,
                seller_client_id=seller_client_id,
                version=cache_version,
                payload=payload,
                source_ref=source_ref,
            )
    if db is not None and not force_refresh:
        payload, source_ref, cache_updated_at = _load_storage_snapshot_from_db(
            db,
            company_name=company_name,
            seller_client_id=seller_client_id,
            version=cache_version,
        )
        source_ref = _ensure_backend_storage_cache_file(
            seller_client_id=seller_client_id,
            version=cache_version,
            payload=payload,
            source_ref=source_ref,
        )
    if not payload:
        payload, _ts, source_path = load_storage_cache_payload(seller_client_id, cache_version)
        cache_updated_at = _ts.isoformat() if _ts is not None else None
        source_ref = str(source_path) if source_path is not None else ""
        source_ref = _ensure_backend_storage_cache_file(
            seller_client_id=seller_client_id,
            version=cache_version,
            payload=payload,
            source_ref=source_ref,
        )
        if db is not None and payload:
            _save_storage_snapshot_to_db(
                db,
                company_name=company_name,
                seller_client_id=seller_client_id,
                version=cache_version,
                payload=payload,
                source_ref=source_ref,
            )
    lot_rows = payload.get("lot_rows", []) if isinstance(payload, dict) else []
    if db is not None and isinstance(payload, dict) and "lot_rows" in payload:
        try:
            sync_shipment_history(
                db,
                company_name=company_name,
                seller_client_id=seller_client_id,
                lot_rows=list(lot_rows) if isinstance(lot_rows, list) else [],
            )
        except Exception:
            pass
    df_lots = pd.DataFrame(lot_rows)
    df_risk = build_fee_risk_forecast_table(df_lots) if not df_lots.empty else pd.DataFrame()

    return {
        "company": company_name,
        "seller_client_id": seller_client_id,
        "cache_updated_at": cache_updated_at,
        "cache_source": source_ref,
        "lot_rows": df_lots.to_dict("records") if not df_lots.empty else [],
        "risk_rows": df_risk.to_dict("records") if not df_risk.empty else [],
        "unknown_stock_rows": payload.get("unknown_stock_rows", []) if isinstance(payload, dict) else [],
        "sku_count": int(payload.get("sku_count", 0) or 0) if isinstance(payload, dict) else 0,
        "order_count": int(payload.get("order_count", 0) or 0) if isinstance(payload, dict) else 0,
        "ship_lot_count": int(payload.get("ship_lot_count", 0) or 0) if isinstance(payload, dict) else 0,
        "stock_articles_count": int(payload.get("stock_articles_count", 0) or 0) if isinstance(payload, dict) else 0,
    }
