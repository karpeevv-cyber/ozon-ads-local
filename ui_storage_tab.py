# -*- coding: utf-8 -*-
from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
import pickle
import traceback

import pandas as pd
import requests
import streamlit as st

_IMPORT_ERROR = ""
try:
    import clients_seller as _cs
except Exception as e:
    _cs = None
    _IMPORT_ERROR = f"{type(e).__name__}: {e}\n{traceback.format_exc()}"


def _require_cs_func(name: str):
    fn = getattr(_cs, name, None) if _cs is not None else None
    if callable(fn):
        return fn
    raise RuntimeError(f"clients_seller.{name} is missing")


def _seller_post_fallback(
    *,
    path: str,
    body: dict,
    client_id: str | None,
    api_key: str | None,
) -> dict:
    base = getattr(_cs, "SELLER_BASE", "https://api-seller.ozon.ru") if _cs is not None else "https://api-seller.ozon.ru"
    headers = {
        "Client-Id": str(client_id or ""),
        "Api-Key": str(api_key or ""),
    }
    if _cs is not None and callable(getattr(_cs, "_post_with_backoff", None)):
        r = _cs._post_with_backoff(f"{base}{path}", headers=headers, body=body, timeout=60)
        return r.json()
    r = requests.post(f"{base}{path}", json=body, headers=headers, timeout=60)
    r.raise_for_status()
    return r.json()


def seller_product_list(**kwargs):
    return _require_cs_func("seller_product_list")(**kwargs)


def seller_product_info_list(**kwargs):
    return _require_cs_func("seller_product_info_list")(**kwargs)


def seller_analytics_stocks(**kwargs):
    return _require_cs_func("seller_analytics_stocks")(**kwargs)


def seller_supply_order_list(**kwargs):
    fn = getattr(_cs, "seller_supply_order_list", None) if _cs is not None else None
    if callable(fn):
        return fn(**kwargs)
    return _seller_post_fallback(
        path="/v3/supply-order/list",
        body={
            "filter": kwargs.get("filter", {}) or {},
            "last_id": str(kwargs.get("last_id", "") or ""),
            "limit": int(kwargs.get("limit", 100)),
            "sort_by": str(kwargs.get("sort_by", "ORDER_CREATION")),
            "sort_dir": str(kwargs.get("sort_dir", "DESC")),
        },
        client_id=kwargs.get("client_id"),
        api_key=kwargs.get("api_key"),
    )


def seller_supply_order_get(**kwargs):
    fn = getattr(_cs, "seller_supply_order_get", None) if _cs is not None else None
    if callable(fn):
        return fn(**kwargs)
    ids = [str(x) for x in (kwargs.get("order_ids") or []) if str(x).strip()]
    return _seller_post_fallback(
        path="/v3/supply-order/get",
        body={"order_ids": ids},
        client_id=kwargs.get("client_id"),
        api_key=kwargs.get("api_key"),
    )


def seller_supply_order_bundle_query(**kwargs):
    fn = getattr(_cs, "seller_supply_order_bundle_query", None) if _cs is not None else None
    if callable(fn):
        return fn(**kwargs)
    body = {
        "bundle_ids": [str(x) for x in (kwargs.get("bundle_ids") or []) if str(x).strip()],
        "is_asc": bool(kwargs.get("is_asc", True)),
        "limit": int(kwargs.get("limit", 100)),
        "sort_field": str(kwargs.get("sort_field", "NAME")),
    }
    storage_ids = [str(x) for x in (kwargs.get("storage_warehouse_ids") or []) if str(x).strip()]
    dropoff_id = str(kwargs.get("dropoff_warehouse_id", "") or "").strip()
    if dropoff_id and storage_ids:
        body["item_tags_calculation"] = {
            "dropoff_warehouse_id": dropoff_id,
            "storage_warehouse_ids": storage_ids,
        }
    last_id = str(kwargs.get("last_id", "") or "").strip()
    if last_id:
        body["last_id"] = last_id
    return _seller_post_fallback(
        path="/v1/supply-order/bundle",
        body=body,
        client_id=kwargs.get("client_id"),
        api_key=kwargs.get("api_key"),
    )


def _chunks(values: list[str], size: int):
    for i in range(0, len(values), size):
        yield values[i : i + size]


def _to_float(v) -> float:
    try:
        return float(v)
    except Exception:
        return 0.0


def _to_dt(v) -> datetime | None:
    if v is None:
        return None
    dt = pd.to_datetime(v, errors="coerce", utc=True)
    if pd.isna(dt):
        return None
    return dt.tz_convert(None).to_pydatetime()


def _norm_city(s: str) -> str:
    txt = str(s or "").strip().upper().replace("Ё", "Е")
    if not txt:
        return "UNKNOWN"
    if "МОСКВА" in txt or "МО И ДАЛЬНИЕ РЕГИОНЫ" in txt or "МО И ДАЛ" in txt:
        return "МОСКВА"
    if "САНКТ-ПЕТЕРБУРГ" in txt or "СЗО" in txt:
        return "САНКТ-ПЕТЕРБУРГ"
    if "ХАБАРОВСК" in txt or txt == "ДАЛЬНИЙ" or "ДАЛЬНИЙ ВОСТОК" in txt:
        return "ДАЛЬНИЙ"
    if txt == "РОСТОВ" or "РОСТОВ-НА-ДОНУ" in txt:
        return "РОСТОВ"
    if txt.startswith("ГРИВНО") or txt.startswith("НОГИНСК") or txt.startswith("ПУШКИНО") or txt.startswith("ХОРУГВИНО") or txt.startswith("ПЕТРОВСКОЕ"):
        return "МОСКВА"
    for suffix in ("_РФЦ_НОВЫЙ", "_МРФЦ", "_РФЦ", "_РЦ"):
        if txt.endswith(suffix):
            txt = txt[: -len(suffix)]
            break
    txt = txt.replace("_1", "").replace("_2", "").strip("_ ").strip()
    if not txt:
        return "UNKNOWN"
    return txt


def _split_tokens(s: str) -> list[str]:
    txt = str(s or "").upper()
    for ch in [",", ".", ";", ":", "/", "\\", "-", "_", "(", ")", "[", "]", "{", "}"]:
        txt = txt.replace(ch, " ")
    return [t for t in txt.split() if t and not t.isdigit()]


def _find_moscow_stock_key(stock_city_keys: set[str]) -> str | None:
    for key in stock_city_keys:
        up = str(key).upper()
        if "МОСК" in up or "MOSCOW" in up or "MOSKVA" in up:
            return key
    return None


def _map_warehouse_city_to_stock_key(warehouse_city: str, stock_city_keys: set[str]) -> str:
    wh_key = _norm_city(warehouse_city)
    if wh_key in stock_city_keys:
        return wh_key
    moscow_key = _find_moscow_stock_key(stock_city_keys)
    wh_tokens = set(_split_tokens(warehouse_city) + _split_tokens(wh_key))
    moscow_aliases = {
        "НОГИНСК", "NOGINSK",
        "ГРИВНО", "GRIVNO", "GRIVNA",
        "ПУШКИНО", "PUSHKINO",
        "ХОРУГВИНО", "HORUGVINO",
        "ПЕТРОВСКОЕ", "PETROVSKOE",
    }
    if moscow_key and (wh_tokens & moscow_aliases):
        return moscow_key

    best_key = ""
    best_score = 0
    for stock_key in stock_city_keys:
        score = len(wh_tokens & set(_split_tokens(stock_key)))
        if score > best_score:
            best_score = score
            best_key = stock_key
    if best_key and best_score > 0:
        return best_key
    return wh_key


MACROLOCAL_CLUSTER_CITY_FALLBACKS = {
    "4039": "МОСКВА",
    "4040": "УФА",
    "4071": "РОСТОВ",
}


def _item_volume_liters_map_for_store(seller_client_id: str | None) -> dict[str, float]:
    # Per-store manual volume dictionary (liters per 1 item).
    if str(seller_client_id or "").strip() == "3319846":  # Aura tea
        return {
            "Шу пуэр лист200": 1.34,
            "Шу пуэр лист100": 0.99,
            "пуэр пресс": 0.56,
            "Black_Ceylon_50": 0.56,
            "Green_Mol_100": 0.99,
            "AURA_TEA_41": 1.34,
            "Black_Ceylon_100": 0.99,
            "Black_Assam_100": 0.99,
            "Green_Te_100": 0.99,
            "Black_Erl_200": 1.34,
            "Green_Te_200": 1.34,
            "Black_Assam_200": 1.34,
            "Black_Erl_100": 0.99,
            "Green_Gan_100": 0.99,
            "Green_Mol_200": 1.34,
            "Black_Ceylon_200": 1.34,
            "Green_Gan_200": 1.34,
            "AURA_TEA_07": 0.56,
            "Black_Erl_50": 0.56,
            "Black_Assam_50": 0.56,
            "Green_Gan_50": 0.56,
            "Green_Mol_50": 0.56,
            "Green_Te_50": 0.56,
        }
    if str(seller_client_id or "").strip() == "3813927":  # Osome tea
        return {
            "Nabor_Green": 1.02,
            "Nabor_black": 1.46,
            "Black_Ceylon_200": 1.15,
            "Green_Te_50": 0.20,
            "Black_Erl_200": 1.47,
            "Green_Mol_200": 0.61,
            "Green_Gan_500": 1.51,
            "Black_Erl_50": 0.43,
            "Green_Te_200": 0.61,
            "Green_Gan_50": 0.20,
            "Black_Ceylon_50": 0.34,
            "Green_Mol_50": 0.20,
            "Green_Gan_200": 0.61,
        }
    return {}


def _load_all_product_ids(
    *,
    seller_client_id: str,
    seller_api_key: str,
    visibility: str = "ALL",
) -> list[str]:
    out: list[str] = []
    last_id = ""
    seen_last_ids: set[str] = set()
    pages = 0
    while True:
        pages += 1
        if pages > 1000:
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
        for it in items:
            pid = it.get("product_id")
            if pid is not None:
                out.append(str(pid))
        next_last_id = str(result.get("last_id", "")) if result.get("last_id") is not None else ""
        if not next_last_id:
            break
        if next_last_id in seen_last_ids:
            break
        seen_last_ids.add(next_last_id)
        last_id = next_last_id
    return list(dict.fromkeys(out))


def _load_sku_offer_map(
    product_ids: list[str],
    *,
    seller_client_id: str,
    seller_api_key: str,
) -> dict[str, str]:
    out: dict[str, str] = {}
    for batch in _chunks(product_ids, 1000):
        resp = seller_product_info_list(
            product_ids=batch,
            client_id=seller_client_id,
            api_key=seller_api_key,
        )
        items = resp.get("items", []) or []
        for it in items:
            sku = it.get("sku")
            if sku is None:
                continue
            out[str(sku)] = str(it.get("offer_id") or "").strip()
    return out


def _city_from_stock_item(it: dict) -> str:
    city = str(it.get("cluster_name") or "").strip()
    if city:
        return city
    cid = it.get("cluster_id")
    return str(cid) if cid is not None else "UNKNOWN"


def _load_stock_by_city_article(
    *,
    seller_client_id: str,
    seller_api_key: str,
) -> tuple[dict[tuple[str, str], float], int, dict[str, str], dict[tuple[str, str], float]]:
    product_ids = _load_all_product_ids(
        seller_client_id=seller_client_id,
        seller_api_key=seller_api_key,
        visibility="ALL",
    )
    if not product_ids:
        product_ids = _load_all_product_ids(
            seller_client_id=seller_client_id,
            seller_api_key=seller_api_key,
            visibility="VISIBLE",
        )
    sku_offer = _load_sku_offer_map(
        product_ids,
        seller_client_id=seller_client_id,
        seller_api_key=seller_api_key,
    )
    skus = [s for s in sku_offer.keys() if str(s).isdigit()]
    stock_map: dict[tuple[str, str], float] = {}
    city_label_by_key: dict[str, str] = {}
    sales_sum_map: dict[tuple[str, str], float] = {}
    sales_cnt_map: dict[tuple[str, str], int] = {}
    for sku_batch in _chunks(skus, 200):
        resp = seller_analytics_stocks(
            skus=sku_batch,
            client_id=seller_client_id,
            api_key=seller_api_key,
        )
        for it in (resp.get("items", []) or []):
            sku = str(it.get("sku") or "").strip()
            if not sku:
                continue
            article = str(it.get("offer_id") or "").strip() or sku_offer.get(sku, "") or sku
            city_raw = _city_from_stock_item(it)
            city = _norm_city(city_raw)
            if city and city not in city_label_by_key:
                city_label_by_key[city] = str(city_raw or city)
            qty = _to_float(it.get("available_stock_count", 0))
            key = (city, article)
            stock_map[key] = stock_map.get(key, 0.0) + qty
            sales = _to_float(it.get("ads_cluster", 0))
            sales_sum_map[key] = sales_sum_map.get(key, 0.0) + sales
            sales_cnt_map[key] = sales_cnt_map.get(key, 0) + 1
    sales_avg_map: dict[tuple[str, str], float] = {}
    for key, sm in sales_sum_map.items():
        cnt = max(1, int(sales_cnt_map.get(key, 1)))
        sales_avg_map[key] = sm / float(cnt)
    return stock_map, len(skus), city_label_by_key, sales_avg_map


def _build_fee_risk_forecast_table(df_lots: pd.DataFrame) -> pd.DataFrame:
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
    group_cols = ["city_key", "article"]
    for (_, _), grp in work.groupby(group_cols, as_index=False):
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
        s = 0.0
        for q in qtys:
            s += float(max(0.0, q))
            prefix.append(s)
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
    out = out.sort_values(
        by=["fee_from_date", "city", "article"],
        ascending=[True, True, True],
        na_position="last",
    )
    return out


def _load_completed_order_ids(
    *,
    seller_client_id: str,
    seller_api_key: str,
) -> list[str]:
    all_states = [
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
    out: list[str] = []
    last_id = ""
    seen_last_ids: set[str] = set()
    pages = 0
    while True:
        pages += 1
        if pages > 2000:
            break
        resp = seller_supply_order_list(
            filter={"states": all_states},
            last_id=last_id,
            limit=100,
            sort_by="ORDER_CREATION",
            sort_dir="DESC",
            client_id=seller_client_id,
            api_key=seller_api_key,
        )
        order_ids = [str(x) for x in (resp.get("order_ids", []) or []) if str(x).strip()]
        if not order_ids:
            break
        out.extend(order_ids)
        next_last_id = str(resp.get("last_id", "") or "")
        if not next_last_id:
            break
        if next_last_id in seen_last_ids:
            break
        seen_last_ids.add(next_last_id)
        last_id = next_last_id
    return list(dict.fromkeys(out))


def _load_orders_by_id(
    *,
    order_ids: list[str],
    seller_client_id: str,
    seller_api_key: str,
) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for batch in _chunks(order_ids, 50):
        try:
            resp = seller_supply_order_get(
                order_ids=batch,
                client_id=seller_client_id,
                api_key=seller_api_key,
            )
        except Exception:
            resp = {"orders": []}
            for order_id in batch:
                try:
                    single_resp = seller_supply_order_get(
                        order_ids=[order_id],
                        client_id=seller_client_id,
                        api_key=seller_api_key,
                    )
                except Exception:
                    continue
                resp["orders"].extend(single_resp.get("orders", []) or [])
        for o in (resp.get("orders", []) or []):
            if not isinstance(o, dict):
                continue
            oid = str(o.get("order_id") or "").strip()
            if oid:
                out[oid] = o
    return out


def _load_bundle_items(
    *,
    bundle_id: str,
    dropoff_warehouse_id: str,
    storage_warehouse_id: str = "",
    seller_client_id: str,
    seller_api_key: str,
) -> list[dict]:
    out: list[dict] = []
    last_id = ""
    pages = 0
    while True:
        pages += 1
        if pages > 1000:
            break
        try:
            resp = seller_supply_order_bundle_query(
                bundle_ids=[str(bundle_id)],
                dropoff_warehouse_id=str(dropoff_warehouse_id),
                storage_warehouse_ids=[str(storage_warehouse_id)] if str(storage_warehouse_id).strip() else [],
                limit=100,
                sort_field="NAME",
                is_asc=True,
                last_id=str(last_id),
                client_id=seller_client_id,
                api_key=seller_api_key,
            )
        except Exception:
            break
        items = resp.get("items", []) or []
        if not items:
            break
        out.extend([x for x in items if isinstance(x, dict)])
        if not bool(resp.get("has_next", False)):
            break
        next_last_id = str(resp.get("last_id", "") or "")
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
                    city = _norm_city(str(row.get("cluster_name") or ""))
                    if city and city != "UNKNOWN":
                        return city
        except Exception:
            pass
    return MACROLOCAL_CLUSTER_CITY_FALLBACKS.get(cluster_id, "UNKNOWN")


def _bundle_items_cache_path(seller_client_id: str) -> Path:
    return Path(f"storage_bundle_items_cache_{seller_client_id}.pkl")


def _load_bundle_items_cache(seller_client_id: str) -> dict[tuple[str, str, str], list[dict]]:
    path = _bundle_items_cache_path(seller_client_id)
    if not path.exists():
        return {}
    try:
        with path.open("rb") as f:
            payload = pickle.load(f) or {}
        if isinstance(payload, dict):
            return payload
    except Exception:
        pass
    return {}


def _save_bundle_items_cache(seller_client_id: str, cache: dict[tuple[str, str, str], list[dict]]) -> None:
    try:
        with _bundle_items_cache_path(seller_client_id).open("wb") as f:
            pickle.dump(cache, f)
    except Exception:
        pass


def _order_lots_cache_path(seller_client_id: str) -> Path:
    return Path(f"storage_order_lots_cache_{seller_client_id}.pkl")


def _load_order_lots_cache(seller_client_id: str) -> dict[str, dict]:
    path = _order_lots_cache_path(seller_client_id)
    if not path.exists():
        return {}
    try:
        with path.open("rb") as f:
            payload = pickle.load(f) or {}
        if isinstance(payload, dict):
            return payload
    except Exception:
        pass
    return {}


def _save_order_lots_cache(seller_client_id: str, cache: dict[str, dict]) -> None:
    try:
        with _order_lots_cache_path(seller_client_id).open("wb") as f:
            pickle.dump(cache, f)
    except Exception:
        pass


def _bootstrap_order_lots_cache_from_storage_cache(seller_client_id: str) -> dict[str, dict]:
    payload, _ts, _source = _load_storage_cache_payload(seller_client_id, "v12")
    lot_rows = payload.get("lot_rows", []) if isinstance(payload, dict) else []
    if not lot_rows:
        return {}
    out: dict[str, dict] = {}
    for row in lot_rows:
        if not isinstance(row, dict):
            continue
        oid = str(row.get("order_id") or "").strip()
        article = str(row.get("article") or "").strip()
        arrival_date = str(row.get("arrival_date") or "").strip()
        if not oid or not article or not arrival_date:
            continue
        try:
            arrival_dt = datetime.fromisoformat(arrival_date)
        except Exception:
            continue
        lot = {
            "city": str(row.get("shipment_city", "") or row.get("storage_warehouse_name", "")).strip(),
            "city_key": str(row.get("city_key", "")).strip(),
            "storage_warehouse_name": str(row.get("storage_warehouse_name", "")).strip(),
            "storage_warehouse_id": str(row.get("storage_warehouse_id", "")).strip(),
            "article": article,
            "order_id": oid,
            "order_number": str(row.get("order_number", "")).strip(),
            "bundle_id": str(row.get("bundle_id", "")).strip(),
            "arrival_dt": arrival_dt,
            "qty": _to_float(row.get("shipped_qty", 0)),
        }
        out.setdefault(oid, {"signature": None, "lots": []})
        out[oid]["lots"].append(lot)
    return out


def _order_signature(order: dict) -> tuple:
    dropoff = order.get("drop_off_warehouse") or {}
    supplies = order.get("supplies", []) or []
    normalized_supplies: list[tuple] = []
    for supply in supplies:
        if not isinstance(supply, dict):
            continue
        storage = supply.get("storage_warehouse") or {}
        normalized_supplies.append(
            (
                str(supply.get("bundle_id") or "").strip(),
                str(supply.get("state") or "").strip().upper(),
                str(storage.get("warehouse_id") or "").strip(),
                str(storage.get("name") or "").strip(),
                str(storage.get("arrival_date") or "").strip(),
            )
        )
    normalized_supplies.sort()
    return (
        str(order.get("order_id") or "").strip(),
        str(order.get("order_number") or "").strip(),
        str(order.get("created_date") or "").strip(),
        str(order.get("state_updated_date") or "").strip(),
        str(dropoff.get("warehouse_id") or "").strip(),
        tuple(normalized_supplies),
    )


def _arrival_dt_for_order(order: dict, supply: dict) -> datetime | None:
    arr = _to_dt((supply.get("storage_warehouse") or {}).get("arrival_date"))
    if arr is not None:
        return arr
    dt = _to_dt(order.get("state_updated_date"))
    if dt is not None:
        return dt
    return _to_dt(order.get("created_date"))


def _build_lots_for_order(
    *,
    oid: str,
    order: dict,
    seller_client_id: str,
    seller_api_key: str,
    bundle_items_cache: dict[tuple[str, str, str], list[dict]],
) -> list[dict]:
    out: list[dict] = []
    dropoff = order.get("drop_off_warehouse") or {}
    dropoff_id = str(dropoff.get("warehouse_id") or "")
    supplies = order.get("supplies", []) or []
    for supply in supplies:
        if not isinstance(supply, dict):
            continue
        storage = supply.get("storage_warehouse") or {}
        storage_id = str(storage.get("warehouse_id") or "")
        storage_name = str(storage.get("name") or "").strip()
        bundle_id = str(supply.get("bundle_id") or "").strip()
        macrolocal_cluster_id = str(supply.get("macrolocal_cluster_id") or "").strip()
        if not bundle_id:
            continue
        arrival_dt = _arrival_dt_for_order(order, supply)
        if arrival_dt is None:
            continue
        bundle_cache_key = (bundle_id, dropoff_id, storage_id or macrolocal_cluster_id)
        items = bundle_items_cache.get(bundle_cache_key)
        if items is None:
            items = _load_bundle_items(
                bundle_id=bundle_id,
                dropoff_warehouse_id=dropoff_id,
                storage_warehouse_id=storage_id,
                seller_client_id=seller_client_id,
                seller_api_key=seller_api_key,
            )
            bundle_items_cache[bundle_cache_key] = items
        if storage_id:
            city = storage_name or storage_id or "UNKNOWN"
            city_key = _norm_city(city)
        else:
            city_key = _city_from_macrolocal_cluster(
                macrolocal_cluster_id=macrolocal_cluster_id,
                items=items,
                seller_client_id=seller_client_id,
                seller_api_key=seller_api_key,
            )
            city = city_key
        for it in items:
            article = str(it.get("offer_id") or "").strip()
            if not article:
                continue
            qty = _to_float(it.get("quantity", 0))
            if qty <= 0:
                continue
            out.append(
                {
                    "city": city,
                    "city_key": city_key,
                    "storage_warehouse_name": storage_name or city,
                    "storage_warehouse_id": storage_id,
                    "article": article,
                    "order_id": str(oid),
                    "order_number": str(order.get("order_number") or ""),
                    "bundle_id": bundle_id,
                    "arrival_dt": arrival_dt,
                    "qty": qty,
                }
            )
    return out


def _build_lots_by_city_article(
    *,
    orders_by_id: dict[str, dict],
    seller_client_id: str,
    seller_api_key: str,
) -> dict[tuple[str, str], list[dict]]:
    lots: dict[tuple[str, str], list[dict]] = {}
    bundle_items_cache = _load_bundle_items_cache(seller_client_id)
    order_lots_cache = _load_order_lots_cache(seller_client_id)
    if not order_lots_cache:
        order_lots_cache = _bootstrap_order_lots_cache_from_storage_cache(seller_client_id)
    bundle_items_cache_changed = False
    order_lots_cache_changed = False
    active_order_ids = {str(oid) for oid in orders_by_id.keys()}
    for oid, order in orders_by_id.items():
        sig = _order_signature(order)
        cached = order_lots_cache.get(str(oid)) or {}
        cached_lots = cached.get("lots", []) or []
        if cached.get("signature") == sig and cached_lots:
            order_lots = cached_lots
        else:
            order_lots = _build_lots_for_order(
                oid=str(oid),
                order=order,
                seller_client_id=seller_client_id,
                seller_api_key=seller_api_key,
                bundle_items_cache=bundle_items_cache,
            )
            order_lots_cache[str(oid)] = {"signature": sig, "lots": order_lots}
            order_lots_cache_changed = True
            bundle_items_cache_changed = True
        for lot in order_lots:
            key = (str(lot.get("city_key") or ""), str(lot.get("article") or ""))
            lots.setdefault(key, []).append(lot)
    stale_order_ids = [oid for oid in list(order_lots_cache.keys()) if oid not in active_order_ids]
    for oid in stale_order_ids:
        order_lots_cache.pop(oid, None)
        order_lots_cache_changed = True
    for key in lots:
        lots[key].sort(key=lambda x: x["arrival_dt"])
    if bundle_items_cache_changed:
        _save_bundle_items_cache(seller_client_id, bundle_items_cache)
    if order_lots_cache_changed:
        _save_order_lots_cache(seller_client_id, order_lots_cache)
    return lots


def _find_storage_cache_files(seller_client_id: str, preferred_version: str) -> list[Path]:
    exact = Path(f"storage_cache_{preferred_version}_{seller_client_id}.pkl")
    other = sorted(
        Path(".").glob(f"storage_cache_v*_{seller_client_id}.pkl"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    out: list[Path] = []
    if exact.exists():
        out.append(exact)
    for path in other:
        if path not in out:
            out.append(path)
    return out


def _load_storage_cache_payload(seller_client_id: str, preferred_version: str) -> tuple[dict, datetime | None, Path | None]:
    for cache_file in _find_storage_cache_files(seller_client_id, preferred_version):
        try:
            with cache_file.open("rb") as f:
                payload = pickle.load(f) or {}
        except Exception:
            continue
        data = payload.get("data", {}) or {}
        ts = payload.get("ts")
        return data, ts, cache_file
    return {}, None, None


def render_storage_tab(
    *,
    seller_client_id: str | None,
    seller_api_key: str | None,
) -> None:
    st.subheader("Storage (shipments, FIFO, 120 days)")
    if _IMPORT_ERROR:
        st.error("Storage dependencies failed to import.")
        st.code(_IMPORT_ERROR)
        return
    if not seller_client_id or not seller_api_key:
        st.warning("Seller creds are missing for selected company.")
        return

    cache_version = "v12"
    cache_key = f"storage:{cache_version}:{seller_client_id}"
    ts_key = f"{cache_key}:ts"
    cache_file = Path(f"storage_cache_{cache_version}_{seller_client_id}.pkl")
    source_key = f"{cache_key}:source"

    btn_cols = st.columns(2)
    load_cached = btn_cols[0].button("Load cached storage", key=f"{cache_key}:load_cached")
    refresh = btn_cols[1].button("Refresh storage", key=f"{cache_key}:refresh")
    current_payload = st.session_state.get(cache_key, {}) or {}
    current_lot_rows = current_payload.get("lot_rows", []) if isinstance(current_payload, dict) else []
    if cache_key not in st.session_state or not current_lot_rows:
        data, ts, source_path = _load_storage_cache_payload(seller_client_id, cache_version)
        if data:
            st.session_state[cache_key] = data
            st.session_state[ts_key] = ts
            st.session_state[source_key] = str(source_path) if source_path is not None else ""

    if load_cached:
        data, ts, source_path = _load_storage_cache_payload(seller_client_id, cache_version)
        if data:
            st.session_state[cache_key] = data
            st.session_state[ts_key] = ts
            st.session_state[source_key] = str(source_path) if source_path is not None else ""
            st.success("Loaded storage from local cache.")
        else:
            st.warning("No local storage cache found for this store.")

    if refresh:
        try:
            with st.spinner("Loading stocks and supply orders..."):
                stock_map, sku_count, stock_city_labels, sales_rate_map = _load_stock_by_city_article(
                    seller_client_id=seller_client_id,
                    seller_api_key=seller_api_key,
                )
                order_ids = _load_completed_order_ids(
                    seller_client_id=seller_client_id,
                    seller_api_key=seller_api_key,
                )
                orders_by_id = _load_orders_by_id(
                    order_ids=order_ids,
                    seller_client_id=seller_client_id,
                    seller_api_key=seller_api_key,
                )
                lots_map = _build_lots_by_city_article(
                    orders_by_id=orders_by_id,
                    seller_client_id=seller_client_id,
                    seller_api_key=seller_api_key,
                )
                now = datetime.now()
                stock_city_keys = set(stock_city_labels.keys())
                article_volume_map = _item_volume_liters_map_for_store(seller_client_id)
                stock_by_city_article: dict[tuple[str, str], float] = {}
                for (city, article), qty in stock_map.items():
                    key = (str(city), str(article))
                    stock_by_city_article[key] = stock_by_city_article.get(key, 0.0) + _to_float(qty)

                all_lots: list[dict] = []
                for lots in lots_map.values():
                    all_lots.extend(lots)

                lots_by_city_article_flat: dict[tuple[str, str], list[dict]] = {}
                for lot in all_lots:
                    city = _map_warehouse_city_to_stock_key(str(lot.get("city", "")), stock_city_keys)
                    article = str(lot.get("article", ""))
                    if not article:
                        continue
                    lot["_mapped_city_key"] = city
                    key = (city, article)
                    lots_by_city_article_flat.setdefault(key, []).append(lot)
                for key in lots_by_city_article_flat:
                    lots_by_city_article_flat[key].sort(key=lambda x: x["arrival_dt"])

                remaining_map: dict[tuple[str, str, str, str, str], float] = {}
                unknown_stock_rows: list[dict] = []
                for (city_key, article), rows in lots_by_city_article_flat.items():
                    current_stock = max(0.0, _to_float(stock_by_city_article.get((city_key, article), 0.0)))
                    need = current_stock
                    for lot in reversed(rows):
                        if need <= 0:
                            break
                        lot_qty = max(0.0, _to_float(lot.get("qty", 0)))
                        take = min(lot_qty, need)
                        if take <= 0:
                            continue
                        k = (
                            str(city_key),
                            str(lot.get("article", "")),
                            str(lot.get("order_id", "")),
                            str(lot.get("bundle_id", "")),
                            lot["arrival_dt"].date().isoformat(),
                        )
                        remaining_map[k] = remaining_map.get(k, 0.0) + take
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
                    fee_from_date = fee_from_dt.date().isoformat()
                    days_until = int(max(0, (fee_from_dt.date() - now.date()).days))
                    mapped_city_key = str(lot.get("_mapped_city_key", _norm_city(str(lot.get("city", "")))))
                    k = (
                        mapped_city_key,
                        article,
                        str(lot.get("order_id", "")),
                        str(lot.get("bundle_id", "")),
                        arrival_date,
                    )
                    qty_remaining = int(round(remaining_map.get(k, 0.0)))
                    lot_rows.append(
                        {
                            "city": stock_city_labels.get(mapped_city_key, mapped_city_key),
                            "shipment_city": str(lot.get("city", "")),
                            "storage_warehouse_name": str(lot.get("storage_warehouse_name", "")),
                            "storage_warehouse_id": str(lot.get("storage_warehouse_id", "")),
                            "article": article,
                            "item_volume_liters": article_volume_map.get(article),
                            "city_key": mapped_city_key,
                            "sales_per_day": round(_to_float(sales_rate_map.get((mapped_city_key, article), 0.0)), 6),
                            "shipped_qty": int(round(_to_float(lot.get("qty", 0)))),
                            "qty_remaining_from_lot": qty_remaining,
                            "in_current_stock": bool(qty_remaining > 0),
                            "arrival_date": arrival_date,
                            "fee_from_date": fee_from_date,
                            "days_until_fee_start": days_until,
                            "fee_started": days_until == 0,
                            "order_id": str(lot.get("order_id", "")),
                            "order_number": str(lot.get("order_number", "")),
                            "bundle_id": str(lot.get("bundle_id", "")),
                        }
                    )
                for row in lot_rows:
                    vol = _to_float(row.get("item_volume_liters"))
                    qty_rem = _to_float(row.get("qty_remaining_from_lot"))
                    fee_started = bool(row.get("fee_started", False))
                    row["daily_storage_fee_rub"] = round(vol * qty_rem * 2.5, 2) if fee_started else 0.0
                    row["projected_storage_fee_rub"] = round(vol * qty_rem * 2.5, 2)

                data = {
                    "lot_rows": lot_rows,
                    "unknown_stock_rows": unknown_stock_rows,
                    "sku_count": sku_count,
                    "order_count": len(order_ids),
                    "ship_lot_count": len(all_lots),
                    "stock_articles_count": len(stock_by_city_article),
                }
                st.session_state[cache_key] = data
                st.session_state[ts_key] = now
                st.session_state[source_key] = str(cache_file)
                try:
                    with cache_file.open("wb") as f:
                        pickle.dump({"data": data, "ts": now}, f)
                except Exception:
                    pass
        except Exception as e:
            st.error(f"Refresh storage failed: {type(e).__name__}: {e}")

    payload = st.session_state.get(cache_key, {}) or {}
    ts = st.session_state.get(ts_key)
    cache_source = str(st.session_state.get(source_key, "") or "")
    if ts:
        st.caption(f"As of: {ts.strftime('%d.%m.%Y %H:%M')}")
    if cache_source and Path(cache_source).name != cache_file.name:
        st.caption(f"Loaded from cache: {Path(cache_source).name}")
    st.caption("FIFO logic: sales consume oldest lots first; fee starts 120 days after lot arrival.")

    lot_rows = payload.get("lot_rows", []) or []
    if not lot_rows:
        st.info("Storage cache is empty. Press Refresh storage to rebuild it.")
        return

    st.caption(
        f"SKUs checked: {payload.get('sku_count', 0)} | "
        f"Completed orders: {payload.get('order_count', 0)} | "
        f"Shipment lots: {payload.get('ship_lot_count', 0)} | "
        f"Stock articles: {payload.get('stock_articles_count', 0)}"
    )

    df_lots = pd.DataFrame(lot_rows)
    cities = (
        sorted(df_lots["city"].dropna().astype(str).unique().tolist())
        if "city" in df_lots.columns
        else []
    )
    city_pick = st.selectbox("City", ["ALL"] + cities, index=0)
    if city_pick != "ALL":
        df_lots = df_lots[df_lots["city"].astype(str) == city_pick].copy()
    articles = (
        sorted(df_lots["article"].dropna().astype(str).unique().tolist())
        if "article" in df_lots.columns
        else []
    )
    article_pick = st.selectbox("Article", ["ALL"] + articles, index=0)
    if article_pick != "ALL":
        df_lots = df_lots[df_lots["article"].astype(str) == article_pick].copy()
    stock_pick = st.selectbox(
        "In current stock",
        ["ALL", "IN_STOCK", "OUT_OF_STOCK"],
        index=0,
    )
    if stock_pick != "ALL" and "in_current_stock" in df_lots.columns:
        if stock_pick == "IN_STOCK":
            df_lots = df_lots[df_lots["in_current_stock"] == True].copy()
        elif stock_pick == "OUT_OF_STOCK":
            df_lots = df_lots[df_lots["in_current_stock"] == False].copy()
    fee_pick = st.selectbox(
        "Fee started",
        ["ALL", "STARTED", "NOT_STARTED"],
        index=0,
    )
    if fee_pick != "ALL" and "fee_started" in df_lots.columns:
        if fee_pick == "STARTED":
            df_lots = df_lots[df_lots["fee_started"] == True].copy()
        elif fee_pick == "NOT_STARTED":
            df_lots = df_lots[df_lots["fee_started"] == False].copy()

    if not df_lots.empty:
        df_lots = df_lots.sort_values(
            by=["fee_from_date", "arrival_date", "city", "article"],
            ascending=[True, True, True, True],
            na_position="last",
        )
    df_risk = _build_fee_risk_forecast_table(df_lots)
    cols = [
        "city",
        "storage_warehouse_name",
        "article",
        "item_volume_liters",
        "shipped_qty",
        "qty_remaining_from_lot",
        "daily_storage_fee_rub",
        "projected_storage_fee_rub",
        "in_current_stock",
        "days_until_fee_start",
        "fee_started",
        "fee_from_date",
        "arrival_date",
    ]
    cols = [c for c in cols if c in df_lots.columns]
    if cols:
        df_lots = df_lots[cols].copy()
        df_lots = df_lots.rename(
            columns={
                "storage_warehouse_name": "warehouse",
            }
        )

    st.markdown("### Shipments Table")
    st.dataframe(df_lots, width="stretch", hide_index=True)

    st.markdown("### Risk Forecast (not sold by fee start)")
    if df_risk.empty:
        st.caption("No risky lots for current filters.")
    else:
        st.dataframe(df_risk, width="stretch", hide_index=True)

    unknown_rows = payload.get("unknown_stock_rows", []) or []
    if unknown_rows:
        df_unknown = pd.DataFrame(unknown_rows)
        if not df_unknown.empty:
            st.warning(
                "Some current stock is larger than total loaded shipment lots for the same article. "
                "Those units cannot be mapped to a specific shipment lot."
            )
            st.dataframe(df_unknown, width="stretch", hide_index=True)
