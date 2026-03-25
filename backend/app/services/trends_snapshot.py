from __future__ import annotations

import json
import pickle
from datetime import date
from pathlib import Path

from sqlalchemy.orm import Session

from app.db.bootstrap import create_all
from app.services.company_config import resolve_company_config
from app.services.storage_paths import backend_data_path, legacy_root_path

from app.services.trends_domain import build_trend_snapshot


def _cache_path(seller_client_id: str | None) -> Path:
    safe_id = (seller_client_id or "default").strip() or "default"
    return backend_data_path(f"trends_snapshot_cache_{safe_id}.pkl")


def _legacy_cache_path(seller_client_id: str | None) -> Path:
    safe_id = (seller_client_id or "default").strip() or "default"
    return legacy_root_path(f"trends_snapshot_cache_{safe_id}.pkl")


def _cache_paths(seller_client_id: str | None) -> list[Path]:
    primary = _cache_path(seller_client_id)
    legacy = _legacy_cache_path(seller_client_id)
    out = [primary]
    if legacy != primary:
        out.append(legacy)
    return out


def _load_cached_snapshot_from_db(
    db: Session,
    *,
    company_name: str,
    seller_client_id: str | None,
    date_from: str,
    date_to: str,
    horizon: str,
    search_filter: str,
) -> dict | None:
    create_all()
    from app.models.trends import TrendsSnapshotCache

    row = (
        db.query(TrendsSnapshotCache)
        .filter(TrendsSnapshotCache.company_name == str(company_name or ""))
        .filter(TrendsSnapshotCache.seller_client_id == str(seller_client_id or ""))
        .filter(TrendsSnapshotCache.date_from == str(date_from))
        .filter(TrendsSnapshotCache.date_to == str(date_to))
        .filter(TrendsSnapshotCache.horizon == str(horizon))
        .filter(TrendsSnapshotCache.search_filter == str(search_filter).strip().lower())
        .order_by(TrendsSnapshotCache.updated_at.desc())
        .first()
    )
    if row is None:
        return None
    try:
        return json.loads(row.snapshot_json)
    except Exception:
        return None


def _save_cached_snapshot_to_db(
    db: Session,
    *,
    company_name: str,
    seller_client_id: str | None,
    date_from: str,
    date_to: str,
    horizon: str,
    search_filter: str,
    signature: tuple,
    snapshot: dict,
) -> None:
    create_all()
    from app.models.trends import TrendsSnapshotCache

    normalized_filter = str(search_filter).strip().lower()
    row = (
        db.query(TrendsSnapshotCache)
        .filter(TrendsSnapshotCache.company_name == str(company_name or ""))
        .filter(TrendsSnapshotCache.seller_client_id == str(seller_client_id or ""))
        .filter(TrendsSnapshotCache.date_from == str(date_from))
        .filter(TrendsSnapshotCache.date_to == str(date_to))
        .filter(TrendsSnapshotCache.horizon == str(horizon))
        .filter(TrendsSnapshotCache.search_filter == normalized_filter)
        .first()
    )
    if row is None:
        row = TrendsSnapshotCache(
            company_name=str(company_name or ""),
            seller_client_id=str(seller_client_id or ""),
            date_from=str(date_from),
            date_to=str(date_to),
            horizon=str(horizon),
            search_filter=normalized_filter,
        )
        db.add(row)
    row.signature_json = json.dumps(list(signature), ensure_ascii=False)
    row.snapshot_json = json.dumps(snapshot, ensure_ascii=False)
    db.commit()


def get_trends_snapshot(
    *,
    company: str | None,
    date_from: str,
    date_to: str,
    horizon: str = "1-3 months",
    search_filter: str = "",
    refresh: bool = False,
    db: Session | None = None,
) -> dict:
    company_name, config = resolve_company_config(company)
    seller_client_id = (config.get("seller_client_id") or "").strip() or None
    seller_api_key = (config.get("seller_api_key") or "").strip() or None

    cache_path = _cache_path(seller_client_id)
    signature = (
        company_name,
        str(date_from),
        str(date_to),
        str(horizon),
        str(search_filter).strip().lower(),
    )

    if refresh:
        for path in _cache_paths(seller_client_id):
            try:
                path.unlink(missing_ok=True)
            except Exception:
                pass

    if db is not None and not refresh:
        snapshot = _load_cached_snapshot_from_db(
            db,
            company_name=company_name,
            seller_client_id=seller_client_id,
            date_from=date_from,
            date_to=date_to,
            horizon=horizon,
            search_filter=search_filter,
        )
        if snapshot:
            meta = dict(snapshot.get("meta") or {})
            meta["cache_source"] = "db-cache"
            snapshot["meta"] = meta
            return snapshot

    for path in _cache_paths(seller_client_id):
        if not path.exists() or refresh:
            continue
        try:
            with path.open("rb") as file:
                cached = pickle.load(file) or {}
            if cached.get("signature") == signature:
                snapshot = dict(cached.get("snapshot") or {})
                meta = dict(snapshot.get("meta") or {})
                meta["cache_source"] = "cache"
                snapshot["meta"] = meta
                return snapshot
        except Exception:
            pass

    snapshot = build_trend_snapshot(
        date_from=date.fromisoformat(date_from),
        date_to=date.fromisoformat(date_to),
        seller_client_id=seller_client_id,
        seller_api_key=seller_api_key,
        horizon=horizon,
        company_name=company_name,
        search_filter=search_filter,
    )
    meta = dict(snapshot.get("meta") or {})
    meta["cache_source"] = "fresh"
    snapshot["meta"] = meta

    if db is not None:
        try:
            _save_cached_snapshot_to_db(
                db,
                company_name=company_name,
                seller_client_id=seller_client_id,
                date_from=date_from,
                date_to=date_to,
                horizon=horizon,
                search_filter=search_filter,
                signature=signature,
                snapshot=snapshot,
            )
        except Exception:
            pass

    try:
        with cache_path.open("wb") as file:
            pickle.dump({"signature": signature, "snapshot": snapshot}, file)
    except Exception:
        pass

    return snapshot
