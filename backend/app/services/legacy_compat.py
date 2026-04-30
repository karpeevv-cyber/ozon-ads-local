from __future__ import annotations

from datetime import datetime
from pathlib import Path
import pickle

import pandas as pd
from app.services.integrations.ozon_seller import (
    seller_analytics_stocks,
    seller_product_info_list,
    seller_product_info_stocks,
    seller_product_list,
)
from app.services.storage_paths import BACKEND_DATA_DIR, REPO_ROOT


def chunked(values: list[str], size: int):
    for i in range(0, len(values), size):
        yield values[i : i + size]


def load_all_product_ids(
    *,
    seller_client_id: str,
    seller_api_key: str,
    visibility: str = "ALL",
) -> list[str]:
    out: list[str] = []
    last_id = ""
    seen_last_ids: set[str] = set()
    max_pages = 1000
    pages = 0
    while True:
        pages += 1
        if pages > max_pages:
            break
        resp = seller_product_list(
            last_id=last_id,
            limit=1000,
            visibility=visibility,
            client_id=seller_client_id,
            api_key=seller_api_key,
        )
        result = resp.get("result", {}) or {}
        items = result.get("items", []) or []
        if not items:
            break
        for item in items:
            product_id = item.get("product_id")
            if product_id is not None:
                out.append(str(product_id))
        next_last_id = str(result.get("last_id", "")) if result.get("last_id") is not None else ""
        if not next_last_id or next_last_id in seen_last_ids:
            break
        seen_last_ids.add(next_last_id)
        last_id = next_last_id
    return list(dict.fromkeys(out))


def load_sku_title_map(
    product_ids: list[str],
    *,
    seller_client_id: str,
    seller_api_key: str,
) -> dict[str, str]:
    sku_title: dict[str, str] = {}
    for batch in chunked(product_ids, 1000):
        resp = seller_product_info_list(
            product_ids=batch,
            client_id=seller_client_id,
            api_key=seller_api_key,
        )
        items = resp.get("items", []) or []
        for item in items:
            sku = item.get("sku")
            name = item.get("name") or item.get("offer_id") or ""
            if sku is not None:
                sku_title[str(sku)] = str(name)
    return sku_title


def load_offer_fbo_present_map(
    offer_ids: list[str],
    *,
    seller_client_id: str,
    seller_api_key: str,
) -> dict[str, int]:
    out: dict[str, int] = {}
    for batch in chunked([offer_id for offer_id in offer_ids if str(offer_id).strip()], 1000):
        resp = seller_product_info_stocks(
            offer_ids=batch,
            client_id=seller_client_id,
            api_key=seller_api_key,
        )
        for item in resp.get("items", []) or []:
            offer_id = str(item.get("offer_id") or "").strip()
            if not offer_id:
                continue
            present = 0
            for stock_item in item.get("stocks", []) or []:
                if str(stock_item.get("type") or "").lower() == "fbo":
                    present += int(float(stock_item.get("present") or 0))
            out[offer_id] = present
    return out


def apply_current_stock_totals(rows: list[dict], fbo_present_by_offer: dict[str, int]) -> None:
    by_offer: dict[str, list[dict]] = {}
    for row in rows:
        offer_id = str(row.get("offer_id") or row.get("article") or "").strip()
        if not offer_id:
            continue
        by_offer.setdefault(offer_id, []).append(row)

    for offer_id, offer_rows in by_offer.items():
        target_total = int(fbo_present_by_offer.get(offer_id, 0) or 0)
        current_total = int(round(sum(float(row.get("available_stock_count") or 0) for row in offer_rows)))
        delta = max(0, target_total - current_total)
        if delta <= 0:
            continue
        transit_rows = sorted(
            [row for row in offer_rows if float(row.get("transit_stock_count") or 0) > 0],
            key=lambda row: float(row.get("transit_stock_count") or 0),
            reverse=True,
        )
        for row in transit_rows:
            if delta <= 0:
                break
            transit_qty = float(row.get("transit_stock_count") or 0)
            moved_qty = min(delta, int(round(transit_qty)))
            if moved_qty <= 0:
                continue
            row["available_stock_count"] = float(row.get("available_stock_count") or 0) + moved_qty
            row["transit_stock_count"] = max(0.0, transit_qty - moved_qty)
            delta -= moved_qty


def build_stocks_rows(
    *,
    seller_client_id: str,
    seller_api_key: str,
) -> tuple[list[dict], int]:
    product_ids = load_all_product_ids(
        seller_client_id=seller_client_id,
        seller_api_key=seller_api_key,
        visibility="ALL",
    )
    if not product_ids:
        product_ids = load_all_product_ids(
            seller_client_id=seller_client_id,
            seller_api_key=seller_api_key,
            visibility="VISIBLE",
        )
    sku_title = load_sku_title_map(
        product_ids,
        seller_client_id=seller_client_id,
        seller_api_key=seller_api_key,
    )
    skus = list(sku_title.keys())
    rows: list[dict] = []
    for sku_batch in chunked(skus, 200):
        resp = seller_analytics_stocks(
            skus=sku_batch,
            client_id=seller_client_id,
            api_key=seller_api_key,
        )
        for item in (resp.get("items", []) or []):
            sku = str(item.get("sku") or "")
            if not sku:
                continue
            cluster_id = item.get("cluster_id")
            cluster_name = item.get("cluster_name") or ""
            turnover_grade = item.get("turnover_grade_cluster") or item.get("turnover_grade") or ""
            full_cluster_label = (
                f"{cluster_id} {cluster_name}".strip() if cluster_id is not None else str(cluster_name).strip()
            )
            parts = full_cluster_label.split()
            cluster_label = parts[1].strip(",.;:") if len(parts) > 1 else full_cluster_label
            if not cluster_label:
                cluster_label = "UNKNOWN"
            rows.append(
                {
                    "sku": sku,
                    "article": item.get("offer_id") or str(sku),
                    "title": item.get("name") or sku_title.get(str(sku), ""),
                    "offer_id": item.get("offer_id") or "",
                    "cluster": cluster_label,
                    "turnover_grade": str(turnover_grade),
                    "available_stock_count": float(item.get("available_stock_count", 0) or 0),
                    "ads_cluster": float(item.get("ads_cluster", 0) or 0),
                    "transit_stock_count": float(item.get("transit_stock_count", 0) or 0),
                }
            )
    fbo_present_by_offer = load_offer_fbo_present_map(
        [str(row.get("offer_id") or row.get("article") or "") for row in rows],
        seller_client_id=seller_client_id,
        seller_api_key=seller_api_key,
    )
    apply_current_stock_totals(rows, fbo_present_by_offer)
    return rows, len(skus)


def find_stocks_cache_files(seller_client_id: str, preferred_version: str = "v2") -> list[Path]:
    search_roots = [BACKEND_DATA_DIR, REPO_ROOT]
    out: list[Path] = []
    for root in search_roots:
        exact = root / f"stocks_cache_{preferred_version}_{seller_client_id}.pkl"
        if exact.exists() and exact not in out:
            out.append(exact)
        other = sorted(
            root.glob(f"stocks_cache_v*_{seller_client_id}.pkl"),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
        for path in other:
            if path not in out:
                out.append(path)
    return out


def load_stocks_cache_payload(
    seller_client_id: str,
    preferred_version: str = "v2",
) -> tuple[list[dict], datetime | None, int]:
    for cache_file in find_stocks_cache_files(seller_client_id, preferred_version):
        try:
            with cache_file.open("rb") as file:
                payload = pickle.load(file) or {}
        except Exception:
            continue
        rows = payload.get("rows", []) or []
        ts = payload.get("ts")
        sku_count = int(payload.get("sku_count", 0) or 0)
        if isinstance(rows, list):
            return rows, ts if isinstance(ts, datetime) else None, sku_count
    return [], None, 0


def save_stocks_cache_payload(
    seller_client_id: str,
    *,
    rows: list[dict],
    sku_count: int,
    version: str = "v2",
) -> datetime:
    ts = datetime.now()
    cache_path = BACKEND_DATA_DIR / f"stocks_cache_{version}_{seller_client_id}.pkl"
    with cache_path.open("wb") as file:
        pickle.dump(
            {
                "rows": rows,
                "ts": ts,
                "sku_count": int(sku_count),
                "rows_count": len(rows),
            },
            file,
        )
    return ts


def build_stocks_rows_cached(
    *,
    seller_client_id: str,
    seller_api_key: str,
    version: str = "v2",
    max_age_hours: int = 24,
) -> tuple[list[dict], int, datetime | None]:
    rows, ts, sku_count = load_stocks_cache_payload(seller_client_id, preferred_version=version)
    if rows and ts is not None:
        age_seconds = (datetime.now() - ts).total_seconds()
        if age_seconds <= max_age_hours * 3600:
            return rows, sku_count, ts

    rows, sku_count = build_stocks_rows(
        seller_client_id=seller_client_id,
        seller_api_key=seller_api_key,
    )
    try:
        ts = save_stocks_cache_payload(
            seller_client_id,
            rows=rows,
            sku_count=sku_count,
            version=version,
        )
    except Exception:
        ts = datetime.now()
    return rows, sku_count, ts


def find_storage_cache_files(seller_client_id: str, preferred_version: str) -> list[Path]:
    search_roots = [BACKEND_DATA_DIR, REPO_ROOT]
    out: list[Path] = []
    for root in search_roots:
        exact = root / f"storage_cache_{preferred_version}_{seller_client_id}.pkl"
        if exact.exists() and exact not in out:
            out.append(exact)
        other = sorted(
            root.glob(f"storage_cache_v*_{seller_client_id}.pkl"),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
        for path in other:
            if path not in out:
                out.append(path)
    return out


def load_storage_cache_payload(seller_client_id: str, preferred_version: str) -> tuple[dict, datetime | None, Path | None]:
    for cache_file in find_storage_cache_files(seller_client_id, preferred_version):
        try:
            with cache_file.open("rb") as file:
                payload = pickle.load(file) or {}
        except Exception:
            continue
        data = payload.get("data", {}) or {}
        ts = payload.get("ts")
        return data, ts, cache_file
    return {}, None, None


def build_fee_risk_forecast_table(df_lots: pd.DataFrame) -> pd.DataFrame:
    need_cols = {
        "city",
        "city_key",
        "article",
        "fee_from_date",
        "days_until_fee_start",
        "qty_remaining_from_lot",
        "item_volume_liters",
        "sales_per_day",
    }
    if df_lots.empty or not need_cols.issubset(set(df_lots.columns)):
        return pd.DataFrame()

    work = df_lots.copy()
    work["qty_remaining_from_lot"] = pd.to_numeric(work["qty_remaining_from_lot"], errors="coerce").fillna(0.0)
    work["item_volume_liters"] = pd.to_numeric(work["item_volume_liters"], errors="coerce").fillna(0.0)
    work["sales_per_day"] = pd.to_numeric(work["sales_per_day"], errors="coerce").fillna(0.0)
    work["days_until_fee_start"] = pd.to_numeric(work["days_until_fee_start"], errors="coerce").fillna(0.0)
    work["fee_from_date_dt"] = pd.to_datetime(work["fee_from_date"], errors="coerce")
    work["arrival_date_dt"] = pd.to_datetime(work.get("arrival_date"), errors="coerce")
    work = work[(work["qty_remaining_from_lot"] > 0) & (work["days_until_fee_start"] <= 90)].copy()
    if work.empty:
        return pd.DataFrame()

    out_rows: list[dict] = []
    for (_, _), grp in work.groupby(["city_key", "article"], as_index=False):
        grp = grp.sort_values(
            by=["arrival_date_dt", "fee_from_date_dt"],
            ascending=[True, True],
            na_position="last",
        ).copy()
        if grp.empty:
            continue
        sales_per_day = float(grp["sales_per_day"].replace([pd.NA], 0).fillna(0).iloc[0])
        sales_per_day = max(0.0, sales_per_day)
        qtys = grp["qty_remaining_from_lot"].tolist()
        prefix: list[float] = []
        total = 0.0
        for qty in qtys:
            total += float(max(0.0, qty))
            prefix.append(total)
        for i, row in enumerate(grp.itertuples(index=False)):
            lot_qty = float(max(0.0, qtys[i]))
            days = max(0.0, float(getattr(row, "days_until_fee_start", 0.0)))
            sold_until_fee = sales_per_day * days
            rem_up_to_i = max(0.0, prefix[i] - sold_until_fee)
            rem_up_to_prev = max(0.0, (prefix[i - 1] if i > 0 else 0.0) - sold_until_fee)
            qty_expected = max(0.0, min(lot_qty, rem_up_to_i - rem_up_to_prev))
            if qty_expected <= 0:
                continue
            unit_volume = float(max(0.0, getattr(row, "item_volume_liters", 0.0)))
            volume_expected = qty_expected * unit_volume
            fee_per_day = volume_expected * 2.5
            out_rows.append(
                {
                    "city": getattr(row, "city", ""),
                    "article": getattr(row, "article", ""),
                    "fee_from_date": getattr(row, "fee_from_date", ""),
                    "days_until_fee_start": int(round(days)),
                    "sales_per_day": round(sales_per_day, 3),
                    "qty_remaining_now": int(round(lot_qty)),
                    "qty_expected_at_fee_start": int(round(qty_expected)),
                    "volume_expected_liters": round(volume_expected, 3),
                    "estimated_daily_fee_rub": round(fee_per_day, 2),
                }
            )
    if not out_rows:
        return pd.DataFrame()
    out = pd.DataFrame(out_rows)
    return out.sort_values(
        by=["fee_from_date", "city", "article"],
        ascending=[True, True, True],
        na_position="last",
    )
