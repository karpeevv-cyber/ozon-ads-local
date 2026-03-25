from __future__ import annotations

from io import StringIO
from pathlib import Path

import pandas as pd
import requests
from sqlalchemy.orm import Session

from app.services.company_config import resolve_company_config
from app.db.bootstrap import create_all
from app.services.integrations.ozon_seller import (
    seller_analytics_data,
    seller_finance_balance,
    seller_product_info_list,
    seller_product_list,
)
from app.services.storage_paths import backend_data_path, legacy_root_path


UNIT_ECON_SOURCES = [
    {
        "seller_client_ids": {"3813927"},
        "company_aliases": {"Osome tea"},
        "sheet_id": "17W18g8mCD2VxtNIOr8EaVM4Hik4cLI444HeFWx31-Ts",
        "gid": "703239472",
    },
    {
        "seller_client_ids": {"3319846"},
        "company_aliases": {"Aura tea"},
        "sheet_id": "1DdBm9Ul__fyUY0hWobwg1fTtIzmILif4ycV_1503R8g",
        "gid": "703239472",
    },
]

SHEET_TEA_COST = "себес порции чая"
SHEET_PACKAGE_COST = "косты уп"
SHEET_PACKAGE_COST_ALT = "косты упаковки"
SHEET_LABEL_COST = "этикетки"
SHEET_LABEL_COST_ALT = "косты этикетки"
SHEET_PACKING_COST = "фасовка"
SHEET_PACKING_COST_ALT = "косты фасовки"


def _to_num(value) -> float:
    if value is None:
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    try:
        text = str(value).strip().replace(" ", "").replace(",", ".")
        return float(text) if text else 0.0
    except Exception:
        return 0.0


def _sheet_csv_url(sheet_id: str, gid: str) -> str:
    return f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv&gid={gid}"


def _normalize_key(value: str | None) -> str:
    return "".join(ch for ch in str(value or "").strip().lower() if ch.isalnum())


def get_unit_econ_sheet_config(company_name: str | None = None, seller_client_id: str | None = None) -> dict[str, str] | None:
    seller_key = _normalize_key(seller_client_id)
    company_key = _normalize_key(company_name)
    for source in UNIT_ECON_SOURCES:
        if seller_key and seller_key in {_normalize_key(v) for v in source.get("seller_client_ids", set())}:
            return {"sheet_id": source["sheet_id"], "gid": source["gid"]}
    for source in UNIT_ECON_SOURCES:
        if company_key and company_key in {_normalize_key(v) for v in source.get("company_aliases", set())}:
            return {"sheet_id": source["sheet_id"], "gid": source["gid"]}
    return None


def get_unit_econ_products_path(company_name: str | None = None, seller_client_id: str | None = None) -> Path:
    safe = _normalize_key(seller_client_id) or _normalize_key(company_name) or "default"
    return backend_data_path(f"unit_economics_products_{safe}.csv")


def _get_unit_econ_products_load_path(company_name: str | None = None, seller_client_id: str | None = None) -> Path:
    primary = get_unit_econ_products_path(company_name=company_name, seller_client_id=seller_client_id)
    if primary.exists():
        return primary
    legacy_candidates = [
        legacy_root_path(primary.name),
        legacy_root_path(
            f"unit_economics_products_{_normalize_key(company_name) or 'default'}.csv"
        ),
    ]
    for legacy in legacy_candidates:
        if legacy != primary and legacy.exists():
            return legacy
    return primary


def _load_unit_cost_overrides(path: Path) -> pd.DataFrame:
    try:
        df = pd.read_csv(path, dtype={"sku": str})
    except Exception:
        return pd.DataFrame(columns=["sku", "position", "tea_cost", "package_cost", "label_cost", "packing_cost"])
    for col in ["sku", "position", "tea_cost", "package_cost", "label_cost", "packing_cost"]:
        if col not in df.columns:
            df[col] = ""
    df["sku"] = df["sku"].astype(str).str.strip()
    df = df[df["sku"].str.fullmatch(r"\d+")].copy()
    return df[["sku", "position", "tea_cost", "package_cost", "label_cost", "packing_cost"]]


def save_unit_cost_overrides(df: pd.DataFrame, path: Path) -> None:
    out = df.copy()
    out["sku"] = out["sku"].astype(str).str.strip()
    out = out[out["sku"].str.fullmatch(r"\d+")].copy()
    out.to_csv(path, index=False, encoding="utf-8-sig")


def _load_unit_cost_overrides_from_db(db: Session, *, company_name: str, seller_client_id: str | None) -> pd.DataFrame:
    create_all()
    from app.models.unit_economics import UnitEconomicsOverride

    rows = (
        db.query(UnitEconomicsOverride)
        .filter(UnitEconomicsOverride.company_name == str(company_name or ""))
        .filter(UnitEconomicsOverride.seller_client_id == str(seller_client_id or ""))
        .all()
    )
    if not rows:
        return pd.DataFrame(columns=["sku", "position", "tea_cost", "package_cost", "label_cost", "packing_cost"])
    return pd.DataFrame(
        [
            {
                "sku": row.sku,
                "position": row.position,
                "tea_cost": row.tea_cost,
                "package_cost": row.package_cost,
                "label_cost": row.label_cost,
                "packing_cost": row.packing_cost,
            }
            for row in rows
        ]
    )


def _save_unit_cost_overrides_to_db(
    db: Session,
    *,
    company_name: str,
    seller_client_id: str | None,
    payload_df: pd.DataFrame,
) -> None:
    create_all()
    from app.models.unit_economics import UnitEconomicsOverride

    scope_company = str(company_name or "")
    scope_seller = str(seller_client_id or "")
    existing_rows = (
        db.query(UnitEconomicsOverride)
        .filter(UnitEconomicsOverride.company_name == scope_company)
        .filter(UnitEconomicsOverride.seller_client_id == scope_seller)
        .all()
    )
    existing_by_sku = {row.sku: row for row in existing_rows}
    incoming_skus = set(payload_df["sku"].astype(str).tolist())

    for sku, row in existing_by_sku.items():
        if sku not in incoming_skus:
            db.delete(row)

    for _, item in payload_df.iterrows():
        sku = str(item["sku"])
        record = existing_by_sku.get(sku)
        if record is None:
            record = UnitEconomicsOverride(
                company_name=scope_company,
                seller_client_id=scope_seller,
                sku=sku,
            )
            db.add(record)
        record.position = str(item["position"] or "")
        record.tea_cost = float(item["tea_cost"] or 0.0)
        record.package_cost = float(item["package_cost"] or 0.0)
        record.label_cost = float(item["label_cost"] or 0.0)
        record.packing_cost = float(item["packing_cost"] or 0.0)
    db.commit()


def _normalize_header(text: str) -> str:
    return str(text or "").strip().lower().replace("ё", "е").replace("\xa0", " ").replace("_", " ")


def _load_unit_costs(sheet_id: str, gid: str) -> pd.DataFrame:
    response = requests.get(_sheet_csv_url(sheet_id, gid), timeout=30)
    response.raise_for_status()
    raw = pd.read_csv(StringIO(response.content.decode("utf-8-sig", errors="replace")), header=None, dtype=str).fillna("")
    if raw.shape[0] < 3:
        return pd.DataFrame(columns=["sku", "sheet_name", "tea_cost", "package_cost", "label_cost", "packing_cost"])

    data = raw.iloc[2:].copy()
    data.columns = [_normalize_header(value) for value in raw.iloc[1].tolist()]
    data["sku"] = data.iloc[:, 0].astype(str).str.strip()
    data = data[data["sku"].str.fullmatch(r"\d+")].copy()
    if data.empty:
        return pd.DataFrame(columns=["sku", "sheet_name", "tea_cost", "package_cost", "label_cost", "packing_cost"])

    empty_series = pd.Series([""] * len(data), index=data.index, dtype=str)
    name_part_1 = data.iloc[:, 1].astype(str).str.strip() if data.shape[1] > 1 else empty_series
    name_part_2 = data.iloc[:, 2].astype(str).str.strip() if data.shape[1] > 2 else empty_series

    def pick(*names: str) -> pd.Series:
        for name in names:
            if name in data.columns:
                found = data[name]
                if isinstance(found, pd.DataFrame):
                    return found.iloc[:, 0]
                return found
        return empty_series

    return pd.DataFrame(
        {
            "sku": data["sku"].astype(str),
            "sheet_name": (name_part_1.fillna("") + " " + name_part_2.fillna("")).str.strip(),
            "tea_cost": pick(SHEET_TEA_COST).apply(_to_num),
            "package_cost": pick(SHEET_PACKAGE_COST, SHEET_PACKAGE_COST_ALT).apply(_to_num),
            "label_cost": pick(SHEET_LABEL_COST, SHEET_LABEL_COST_ALT).apply(_to_num),
            "packing_cost": pick(SHEET_PACKING_COST, SHEET_PACKING_COST_ALT).apply(_to_num),
        }
    )


def load_effective_unit_costs(company_name: str | None, seller_client_id: str | None = None, db: Session | None = None) -> pd.DataFrame:
    config = get_unit_econ_sheet_config(company_name=company_name, seller_client_id=seller_client_id)
    if not config:
        return pd.DataFrame(columns=["sku", "sheet_name", "tea_cost", "package_cost", "label_cost", "packing_cost"])
    base = _load_unit_costs(config["sheet_id"], config["gid"]).copy()
    overrides = pd.DataFrame(columns=["sku", "position", "tea_cost", "package_cost", "label_cost", "packing_cost"])
    if db is not None:
        try:
            overrides = _load_unit_cost_overrides_from_db(
                db,
                company_name=str(company_name or ""),
                seller_client_id=seller_client_id,
            ).copy()
        except Exception:
            overrides = pd.DataFrame(columns=["sku", "position", "tea_cost", "package_cost", "label_cost", "packing_cost"])
    if overrides.empty:
        overrides = _load_unit_cost_overrides(
            _get_unit_econ_products_load_path(company_name=company_name, seller_client_id=seller_client_id)
        ).copy()
    if overrides.empty:
        return base
    overrides["position"] = overrides["position"].astype(str).fillna("").str.strip()
    for col in ["tea_cost", "package_cost", "label_cost", "packing_cost"]:
        overrides[col] = pd.to_numeric(overrides[col], errors="coerce")
    merged = base.merge(overrides, on="sku", how="outer", suffixes=("", "__override"))
    merged["sheet_name"] = merged.get("position", "").where(
        merged.get("position", "").astype(str).str.strip().ne(""),
        merged.get("sheet_name", "").astype(str),
    )
    for col in ["tea_cost", "package_cost", "label_cost", "packing_cost"]:
        override_col = f"{col}__override"
        if override_col in merged.columns:
            merged[col] = merged[override_col].where(merged[override_col].notna(), merged[col])
    return merged[["sku", "sheet_name", "tea_cost", "package_cost", "label_cost", "packing_cost"]].copy()


def _load_saved_unit_cost_overrides(
    *,
    company_name: str | None,
    seller_client_id: str | None,
    db: Session | None = None,
) -> pd.DataFrame:
    if db is not None:
        try:
            overrides = _load_unit_cost_overrides_from_db(
                db,
                company_name=str(company_name or ""),
                seller_client_id=seller_client_id,
            ).copy()
            if not overrides.empty:
                return overrides
        except Exception:
            pass
    return _load_unit_cost_overrides(
        _get_unit_econ_products_load_path(company_name=company_name, seller_client_id=seller_client_id)
    ).copy()


def _load_sales_by_sku_day_rows(date_from: str, date_to: str, *, seller_client_id: str | None, seller_api_key: str | None) -> pd.DataFrame:
    rows: list[dict] = []
    offset = 0
    limit = 1000
    while True:
        payload = seller_analytics_data(
            date_from=date_from,
            date_to=date_to,
            dimension=["sku", "day"],
            metrics=["revenue", "ordered_units"],
            limit=limit,
            offset=offset,
            client_id=seller_client_id,
            api_key=seller_api_key,
        )
        data = (payload.get("result", {}) or {}).get("data", []) or []
        if not data:
            break
        for item in data:
            dims = item.get("dimensions", []) or []
            metrics = item.get("metrics", []) or []
            rows.append(
                {
                    "sku": str((dims[0] or {}).get("id", "")).strip() if len(dims) > 0 else "",
                    "name": str((dims[0] or {}).get("name", "")).strip() if len(dims) > 0 else "",
                    "day": str((dims[1] or {}).get("id", "")).strip() if len(dims) > 1 else "",
                    "revenue": _to_num(metrics[0] if len(metrics) > 0 else 0),
                    "ordered_units": int(round(_to_num(metrics[1] if len(metrics) > 1 else 0))),
                }
            )
        if len(data) < limit:
            break
        offset += limit
    df = pd.DataFrame(rows)
    if df.empty:
        return pd.DataFrame(columns=["sku", "name", "day", "revenue", "ordered_units"])
    return df[df["sku"].astype(str).str.strip().ne("")].copy()


def _load_sales_by_sku(date_from: str, date_to: str, *, seller_client_id: str | None, seller_api_key: str | None) -> pd.DataFrame:
    df = _load_sales_by_sku_day_rows(date_from, date_to, seller_client_id=seller_client_id, seller_api_key=seller_api_key)
    if df.empty:
        return pd.DataFrame(columns=["sku", "name", "quantity", "revenue", "sale"])
    grouped = df.groupby("sku", as_index=False).agg(quantity=("ordered_units", "sum"), revenue=("revenue", "sum"), name=("name", "first"))
    grouped = grouped[grouped["quantity"] > 0].copy()
    grouped["sale"] = grouped.apply(
        lambda row: float(row["revenue"]) / float(row["quantity"]) if float(row["quantity"]) > 0 else 0.0,
        axis=1,
    )
    return grouped


def _load_finance_period_costs(date_from: str, date_to: str, *, seller_client_id: str | None, seller_api_key: str | None) -> dict[str, float]:
    payload = seller_finance_balance(date_from=date_from, date_to=date_to, client_id=seller_client_id, api_key=seller_api_key)
    services = ((payload.get("cashflows", {}) or {}).get("services", [])) or []
    out = {
        "logistics": 0.0,
        "cross_docking": 0.0,
        "acceptance": 0.0,
        "marketing": 0.0,
        "promotion_with_cpo": 0.0,
        "acquiring": 0.0,
        "reverse_logistics": 0.0,
        "returns_processing": 0.0,
        "errors": 0.0,
        "storage": 0.0,
        "points_for_reviews": 0.0,
        "seller_bonuses": 0.0,
    }
    for service in services:
        name = str(service.get("name", "") or "").strip()
        value = abs(_to_num((service.get("amount", {}) or {}).get("value", 0)))
        if name in {"logistics", "courier_client_reinvoice"}:
            out["logistics"] += value
        elif name == "cross_docking":
            out["cross_docking"] += value
        elif name == "goods_processing_in_shipment":
            out["acceptance"] += value
        elif name == "pay_per_click":
            out["marketing"] += value
        elif name == "promotion_with_cost_per_order":
            out["promotion_with_cpo"] += value
        elif name == "acquiring":
            out["acquiring"] += value
        elif name == "reverse_logistics":
            out["reverse_logistics"] += value
        elif name == "partner_returns_cancellations_processing":
            out["returns_processing"] += value
        elif name == "booking_space_and_staff_for_partial_shipment":
            out["errors"] += value
        elif name == "product_placement_in_ozon_warehouses":
            out["storage"] += value
        elif name == "points_for_reviews":
            out["points_for_reviews"] += value
        elif name == "seller_bonuses":
            out["seller_bonuses"] += value
    return out


def _apply_unit_econ_costs(sales_df: pd.DataFrame, costs_df: pd.DataFrame, finance_costs: dict[str, float]) -> pd.DataFrame:
    if sales_df.empty:
        return pd.DataFrame()
    total_units = float(pd.to_numeric(sales_df["quantity"], errors="coerce").fillna(0).sum())
    if total_units <= 0:
        return pd.DataFrame()
    merged = sales_df.merge(costs_df, on="sku", how="left")
    merged["position"] = merged["name"].astype(str).str.strip()
    missing_name = merged["position"].eq("")
    merged.loc[missing_name, "position"] = merged.loc[missing_name, "sheet_name"].astype(str).str.strip()
    for col in ["tea_cost", "package_cost", "label_cost", "packing_cost"]:
        merged[col] = pd.to_numeric(merged[col], errors="coerce").fillna(0.0)
    merged["delivery_fbo"] = (finance_costs["cross_docking"] + finance_costs["acceptance"]) / total_units
    merged["promotion"] = (finance_costs["marketing"] + finance_costs["promotion_with_cpo"]) / total_units
    merged["ozon_percent_cost"] = merged["sale"].apply(lambda value: float(value) * (0.20 if float(value) <= 300 else 0.31))
    merged["ozon_logistics"] = finance_costs["logistics"] / total_units
    merged["other_costs"] = (
        finance_costs["acquiring"]
        + finance_costs["reverse_logistics"]
        + finance_costs["returns_processing"]
        + finance_costs["errors"]
        + finance_costs["storage"]
    ) / total_units
    merged["review_points"] = finance_costs["points_for_reviews"] / total_units
    merged["seller_bonuses"] = finance_costs["seller_bonuses"] / total_units
    merged["taxes"] = merged["sale"].astype(float) * 0.025
    merged["EBITDA"] = (
        merged["sale"].astype(float)
        - merged["tea_cost"]
        - merged["package_cost"]
        - merged["label_cost"]
        - merged["packing_cost"]
        - merged["delivery_fbo"]
        - merged["promotion"]
        - merged["ozon_percent_cost"]
        - merged["ozon_logistics"]
        - merged["other_costs"]
        - merged["review_points"]
        - merged["seller_bonuses"]
        - merged["taxes"]
    )
    merged["ebitda_pct"] = merged.apply(
        lambda row: (float(row["EBITDA"]) / float(row["sale"]) * 100.0) if float(row["sale"]) else 0.0,
        axis=1,
    )
    return merged


def _build_day_sales(raw_sales_df: pd.DataFrame) -> pd.DataFrame:
    if raw_sales_df.empty:
        return pd.DataFrame()
    day_sales_df = raw_sales_df.groupby(["day", "sku"], as_index=False).agg(
        quantity=("ordered_units", "sum"),
        revenue=("revenue", "sum"),
        name=("name", "first"),
    )
    day_sales_df = day_sales_df[day_sales_df["quantity"] > 0].copy()
    if day_sales_df.empty:
        return pd.DataFrame()
    day_sales_df["sale"] = day_sales_df.apply(
        lambda row: float(row["revenue"]) / float(row["quantity"]) if float(row["quantity"]) > 0 else 0.0,
        axis=1,
    )
    return day_sales_df


def _load_all_product_ids(*, seller_client_id: str, seller_api_key: str) -> list[str]:
    out: list[str] = []
    last_id = ""
    seen_last_ids: set[str] = set()
    while True:
        response = seller_product_list(last_id=last_id, limit=1000, visibility="ALL", client_id=seller_client_id, api_key=seller_api_key)
        result = response.get("result", {}) or {}
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


def _load_sku_title_map(*, seller_client_id: str, seller_api_key: str) -> dict[str, str]:
    product_ids = _load_all_product_ids(seller_client_id=seller_client_id, seller_api_key=seller_api_key)
    if not product_ids:
        return {}
    out: dict[str, str] = {}
    for i in range(0, len(product_ids), 1000):
        batch = product_ids[i : i + 1000]
        response = seller_product_info_list(product_ids=batch, client_id=seller_client_id, api_key=seller_api_key)
        for item in response.get("items", []) or []:
            sku = item.get("sku")
            if sku is not None:
                out[str(sku)] = str(item.get("name") or item.get("offer_id") or "").strip()
    return out


def get_unit_economics_summary(*, company: str | None, date_from: str, date_to: str, db: Session | None = None) -> dict:
    company_name, config = resolve_company_config(company)
    seller_client_id = (config.get("seller_client_id") or "").strip() or None
    seller_api_key = (config.get("seller_api_key") or "").strip() or None
    costs_df = load_effective_unit_costs(company_name, seller_client_id=seller_client_id, db=db)
    raw_sales_df = _load_sales_by_sku_day_rows(date_from, date_to, seller_client_id=seller_client_id, seller_api_key=seller_api_key)
    day_sales_df = _build_day_sales(raw_sales_df)
    if costs_df.empty or day_sales_df.empty:
        return {
            "company": company_name,
            "date_from": date_from,
            "date_to": date_to,
            "rows": [],
            "totals": {},
        }

    rows: list[dict] = []
    for day_str in sorted(day_sales_df["day"].astype(str).unique().tolist()):
        sales_day = day_sales_df[day_sales_df["day"].astype(str) == str(day_str)].copy()
        finance_costs = _load_finance_period_costs(str(day_str), str(day_str), seller_client_id=seller_client_id, seller_api_key=seller_api_key)
        applied = _apply_unit_econ_costs(sales_day, costs_df, finance_costs)
        if applied.empty:
            continue
        qty = pd.to_numeric(applied["quantity"], errors="coerce").fillna(0.0)
        rows.append(
            {
                "day": str(day_str),
                "revenue": float(pd.to_numeric(applied["revenue"], errors="coerce").fillna(0.0).sum()),
                "ebitda_total": float((pd.to_numeric(applied["EBITDA"], errors="coerce").fillna(0.0) * qty).sum()),
                "tea_cost": float((pd.to_numeric(applied["tea_cost"], errors="coerce").fillna(0.0) * qty).sum()),
                "package_cost": float((pd.to_numeric(applied["package_cost"], errors="coerce").fillna(0.0) * qty).sum()),
                "label_cost": float((pd.to_numeric(applied["label_cost"], errors="coerce").fillna(0.0) * qty).sum()),
                "packing_cost": float((pd.to_numeric(applied["packing_cost"], errors="coerce").fillna(0.0) * qty).sum()),
                "delivery_fbo": float((pd.to_numeric(applied["delivery_fbo"], errors="coerce").fillna(0.0) * qty).sum()),
                "promotion": float((pd.to_numeric(applied["promotion"], errors="coerce").fillna(0.0) * qty).sum()),
                "ozon_percent_cost": float((pd.to_numeric(applied["ozon_percent_cost"], errors="coerce").fillna(0.0) * qty).sum()),
                "ozon_logistics": float((pd.to_numeric(applied["ozon_logistics"], errors="coerce").fillna(0.0) * qty).sum()),
                "other_costs": float((pd.to_numeric(applied["other_costs"], errors="coerce").fillna(0.0) * qty).sum()),
                "review_points": float((pd.to_numeric(applied["review_points"], errors="coerce").fillna(0.0) * qty).sum()),
                "seller_bonuses": float((pd.to_numeric(applied["seller_bonuses"], errors="coerce").fillna(0.0) * qty).sum()),
                "taxes": float((pd.to_numeric(applied["taxes"], errors="coerce").fillna(0.0) * qty).sum()),
                "units_sold": float(qty.sum()),
            }
        )
    revenue_total = sum(float(row["revenue"]) for row in rows)
    totals = {key: 0.0 for key in rows[0].keys() if key != "day"} if rows else {}
    for row in rows:
        for key, value in row.items():
            if key != "day":
                totals[key] = totals.get(key, 0.0) + float(value)
    totals_pct: dict[str, float | str] = {}
    for key, value in totals.items():
        if key == "units_sold":
            totals_pct[key] = ""
        elif key == "revenue":
            totals_pct[key] = 100.0 if revenue_total else 0.0
        else:
            totals_pct[key] = (float(value) / revenue_total * 100.0) if revenue_total else 0.0
    return {
        "company": company_name,
        "date_from": date_from,
        "date_to": date_to,
        "rows": rows,
        "totals": totals,
        "totals_pct": totals_pct,
    }


def get_unit_economics_products(*, company: str | None, date_from: str, date_to: str, db: Session | None = None) -> dict:
    company_name, config = resolve_company_config(company)
    seller_client_id = (config.get("seller_client_id") or "").strip() or None
    seller_api_key = (config.get("seller_api_key") or "").strip() or None
    if not seller_client_id or not seller_api_key:
        return {"company": company_name, "date_from": date_from, "date_to": date_to, "rows": []}

    costs_df = load_effective_unit_costs(company_name, seller_client_id=seller_client_id, db=db).rename(columns={"sheet_name": "sheet_title"})
    if costs_df.empty:
        return {"company": company_name, "date_from": date_from, "date_to": date_to, "rows": []}

    sales_df = _load_sales_by_sku(date_from, date_to, seller_client_id=seller_client_id, seller_api_key=seller_api_key)
    sku_title_map = _load_sku_title_map(seller_client_id=seller_client_id, seller_api_key=seller_api_key)
    overrides_df = _load_saved_unit_cost_overrides(
        company_name=company_name,
        seller_client_id=seller_client_id,
        db=db,
    )

    sales_name_df = pd.DataFrame(columns=["sku", "sales_name"])
    if not sales_df.empty and "name" in sales_df.columns:
        sales_name_df = sales_df[["sku", "name"]].rename(columns={"name": "sales_name"})

    view_df = costs_df.merge(sales_name_df, on="sku", how="left")
    if not overrides_df.empty:
        view_df = view_df.merge(overrides_df[["sku", "position"]].rename(columns={"position": "saved_name"}), on="sku", how="left")
    else:
        view_df["saved_name"] = ""

    view_df["ozon_name"] = view_df["sku"].astype(str).map(sku_title_map).fillna("").astype(str).str.strip()
    view_df["sales_name"] = view_df["sales_name"].fillna("").astype(str).str.strip()
    view_df["saved_name"] = view_df["saved_name"].fillna("").astype(str).str.strip()
    view_df["sheet_title"] = view_df["sheet_title"].fillna("").astype(str).str.strip()
    view_df["name"] = view_df["ozon_name"]
    for source_col in ["sales_name", "saved_name", "sheet_title"]:
        missing = view_df["name"].eq("")
        view_df.loc[missing, "name"] = view_df.loc[missing, source_col]

    for col in ["tea_cost", "package_cost", "label_cost", "packing_cost"]:
        view_df[col] = pd.to_numeric(view_df[col], errors="coerce").fillna(0.0)

    rows = (
        view_df[["sku", "name", "tea_cost", "package_cost", "label_cost", "packing_cost"]]
        .sort_values(["sku"], ascending=[True])
        .to_dict("records")
    )
    return {"company": company_name, "date_from": date_from, "date_to": date_to, "rows": rows}


def update_unit_economics_products(*, company: str | None, rows: list[dict], db: Session | None = None) -> dict:
    company_name, config = resolve_company_config(company)
    seller_client_id = (config.get("seller_client_id") or "").strip() or None
    path = get_unit_econ_products_path(company_name=company_name, seller_client_id=seller_client_id)
    existing = _load_saved_unit_cost_overrides(
        company_name=company_name,
        seller_client_id=seller_client_id,
        db=db,
    )
    payload_df = pd.DataFrame(rows or [])
    if payload_df.empty:
        payload_df = pd.DataFrame(columns=["sku", "position", "tea_cost", "package_cost", "label_cost", "packing_cost"])
    for col in ["sku", "position", "tea_cost", "package_cost", "label_cost", "packing_cost"]:
        if col not in payload_df.columns:
            payload_df[col] = ""
    payload_df = payload_df[["sku", "position", "tea_cost", "package_cost", "label_cost", "packing_cost"]].copy()
    payload_df["sku"] = payload_df["sku"].astype(str).str.strip()
    payload_df["position"] = payload_df["position"].astype(str).str.strip()
    for col in ["tea_cost", "package_cost", "label_cost", "packing_cost"]:
        payload_df[col] = pd.to_numeric(payload_df[col], errors="coerce").fillna(0.0)

    if existing.empty:
        merged = payload_df
    else:
        existing = existing[~existing["sku"].isin(payload_df["sku"].astype(str))].copy()
        merged = pd.concat([existing, payload_df], ignore_index=True)

    if db is not None:
        _save_unit_cost_overrides_to_db(
            db,
            company_name=company_name,
            seller_client_id=seller_client_id,
            payload_df=merged,
        )
    save_unit_cost_overrides(merged, path)
    result_rows = (
        merged.sort_values(["sku"], ascending=[True])
        .rename(columns={"position": "name"})
        [["sku", "name", "tea_cost", "package_cost", "label_cost", "packing_cost"]]
        .to_dict("records")
    )
    return {"company": company_name, "rows": result_rows, "saved_count": len(payload_df)}
