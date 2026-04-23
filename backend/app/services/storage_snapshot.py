from __future__ import annotations

import json
import shutil

import pandas as pd
from sqlalchemy.orm import Session

from app.db.bootstrap import create_all
from app.services.company_config import resolve_company_config
from app.services.legacy_compat import build_fee_risk_forecast_table, load_storage_cache_payload
from app.services.shipment_history import sync_shipment_history
from app.services.storage_paths import REPO_ROOT, backend_data_path


def _load_storage_snapshot_from_db(
    db: Session,
    *,
    company_name: str,
    seller_client_id: str,
    version: str,
) -> tuple[dict, str]:
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
        return {}, ""
    try:
        return json.loads(row.snapshot_json), str(row.source_ref or "")
    except Exception:
        return {}, ""


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


def get_storage_snapshot(*, company: str | None = None, db: Session | None = None) -> dict:
    company_name, config = resolve_company_config(company)
    seller_client_id = (config.get("seller_client_id") or "").strip()
    cache_version = "v12"

    if not seller_client_id:
        return {
            "company": company_name,
            "seller_client_id": seller_client_id,
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
    if db is not None:
        payload, source_ref = _load_storage_snapshot_from_db(
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
        "lot_rows": df_lots.to_dict("records") if not df_lots.empty else [],
        "risk_rows": df_risk.to_dict("records") if not df_risk.empty else [],
        "unknown_stock_rows": payload.get("unknown_stock_rows", []) if isinstance(payload, dict) else [],
        "sku_count": int(payload.get("sku_count", 0) or 0) if isinstance(payload, dict) else 0,
        "order_count": int(payload.get("order_count", 0) or 0) if isinstance(payload, dict) else 0,
        "ship_lot_count": int(payload.get("ship_lot_count", 0) or 0) if isinstance(payload, dict) else 0,
        "stock_articles_count": int(payload.get("stock_articles_count", 0) or 0) if isinstance(payload, dict) else 0,
    }
