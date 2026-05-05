from __future__ import annotations

import csv
import json
import logging
import os
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd
import requests


BID_LOG_COLUMNS = [
    "ts_iso",
    "date",
    "campaign_id",
    "sku",
    "old_bid_micro",
    "new_bid_micro",
    "reason",
    "comment",
]
CAMPAIGN_COMMENT_SKU = "__campaign_comment__"
TZ_DEFAULT = ZoneInfo("Europe/Moscow")
GSHEET_BACKEND_NAME = "gsheets"
GIST_BACKEND_NAME = "gist"
logger = logging.getLogger("ozon_ads")


@dataclass(frozen=True)
class BidApplyResult:
    old_bid_micro: int | None
    new_bid_micro: int
    reason: str


def rub_to_micro(rub_value: float) -> int:
    return int(round(float(rub_value) * 1_000_000))


def ensure_bid_log(path: str) -> None:
    if _use_gist_backend():
        return
    if _use_gsheet_backend():
        try:
            _ensure_gsheet_log()
            return
        except Exception:
            pass
    if os.path.exists(path):
        return
    with open(path, "w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=BID_LOG_COLUMNS, delimiter=";")
        writer.writeheader()


def append_bid_change(
    *,
    campaign_id: str,
    sku: str,
    old_bid_micro: int | None,
    new_bid_micro: int,
    reason: str,
    comment: str = "",
    path: str,
    tz: ZoneInfo = TZ_DEFAULT,
) -> None:
    ensure_bid_log(path)
    now = datetime.now(tz)
    payload = {
        "ts_iso": now.isoformat(),
        "date": now.date().isoformat(),
        "campaign_id": str(campaign_id),
        "sku": str(sku),
        "old_bid_micro": "" if old_bid_micro is None else str(int(old_bid_micro)),
        "new_bid_micro": str(int(new_bid_micro)),
        "reason": str(reason),
        "comment": str(comment),
    }
    if _use_gsheet_backend():
        try:
            _append_gsheet_row(payload)
            return
        except Exception:
            pass
    if _use_gist_backend():
        _append_gist_row(payload)
        return
    with open(path, "a", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=BID_LOG_COLUMNS, delimiter=";")
        writer.writerow(payload)


def append_campaign_comment(
    *,
    campaign_id: str,
    comment: str,
    day: date | None,
    company: str | None,
    path: str,
    tz: ZoneInfo = TZ_DEFAULT,
) -> None:
    ensure_bid_log(path)
    now = datetime.now(tz)
    payload = {
        "ts_iso": now.isoformat(),
        "date": (day or now.date()).isoformat(),
        "campaign_id": str(campaign_id),
        "sku": CAMPAIGN_COMMENT_SKU,
        "old_bid_micro": "",
        "new_bid_micro": "",
        "reason": str(company or "").strip(),
        "comment": str(comment or "").strip(),
    }
    if _use_gsheet_backend():
        try:
            _append_gsheet_row(payload)
            return
        except Exception:
            pass
    if _use_gist_backend():
        _append_gist_row(payload)
        return
    with open(path, "a", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=BID_LOG_COLUMNS, delimiter=";")
        writer.writerow(payload)


def load_campaign_comments_from_bid_log(path: str) -> pd.DataFrame:
    if _use_gist_backend():
        df = _load_gist_rows()
    else:
        if not os.path.exists(path):
            return pd.DataFrame(columns=["ts", "day", "week", "company", "campaign_id", "comment"])
        df = pd.read_csv(path, sep=";", encoding="utf-8", dtype=str).fillna("")

    for column in BID_LOG_COLUMNS:
        if column not in df.columns:
            df[column] = ""

    comments = df[df["sku"].astype(str) == CAMPAIGN_COMMENT_SKU].copy()
    if comments.empty:
        return pd.DataFrame(columns=["ts", "day", "week", "company", "campaign_id", "comment"])

    comments["ts"] = comments["ts_iso"].astype(str)
    comments["day"] = comments["date"].astype(str)
    comments["week"] = comments["day"].apply(_week_start_iso)
    comments["company"] = comments["reason"].astype(str)
    comments["campaign_id"] = comments["campaign_id"].astype(str)
    comments["comment"] = comments["comment"].astype(str)
    return comments[["ts", "day", "week", "company", "campaign_id", "comment"]].copy()


def load_bid_changes(path: str) -> pd.DataFrame:
    if _use_gist_backend():
        df = _load_gist_rows()
    elif _use_gsheet_backend():
        try:
            df = _load_gsheet_rows()
        except Exception:
            df = pd.DataFrame(columns=BID_LOG_COLUMNS)
    else:
        if not os.path.exists(path):
            return pd.DataFrame(columns=BID_LOG_COLUMNS)
        df = pd.read_csv(path, sep=";", encoding="utf-8", dtype=str).fillna("")

    for column in BID_LOG_COLUMNS:
        if column not in df.columns:
            df[column] = ""

    out = df[df["sku"].astype(str) != CAMPAIGN_COMMENT_SKU].copy()
    out["old_bid_micro"] = out["old_bid_micro"].apply(_to_int_or_none).astype("Int64")
    out["new_bid_micro"] = out["new_bid_micro"].apply(_to_int_or_none).astype("Int64")
    return out[BID_LOG_COLUMNS].copy()


def fetch_old_bid_micro_from_products(products: list[dict], sku: str) -> int | None:
    sku = str(sku)
    for product in products or []:
        if str(product.get("sku")) != sku:
            continue
        raw = product.get("current_bid")
        if raw is None:
            raw = product.get("currentBid")
        if raw is None:
            raw = product.get("bid")
        if raw is None:
            return None
        try:
            return int(float(str(raw).strip().replace(" ", "").replace(",", ".")))
        except Exception:
            return None
    return None


def apply_bid_and_log(
    *,
    token: str,
    campaign_id: str,
    sku: str,
    bid_rub: float,
    reason: str,
    comment: str,
    products_loader,
    bid_updater,
    log_path: str,
) -> BidApplyResult:
    campaign_id = str(campaign_id)
    sku = str(sku).strip()
    reason = str(reason).strip()

    products = products_loader(token, campaign_id)
    old_bid_micro = fetch_old_bid_micro_from_products(products, sku)
    new_bid_micro = rub_to_micro(bid_rub)

    bid_updater(token, campaign_id, bids=[{"sku": sku, "bid": str(new_bid_micro)}])
    append_bid_change(
        campaign_id=campaign_id,
        sku=sku,
        old_bid_micro=old_bid_micro,
        new_bid_micro=new_bid_micro,
        reason=reason,
        comment=comment,
        path=log_path,
    )
    return BidApplyResult(old_bid_micro=old_bid_micro, new_bid_micro=new_bid_micro, reason=reason)


def _to_int_or_none(value) -> int | None:
    if value is None:
        return None
    if isinstance(value, int):
        return int(value)
    text = str(value).strip()
    if not text or text.lower() in {"nan", "none", "<na>"}:
        return None
    try:
        return int(float(text.replace(" ", "").replace(",", ".")))
    except Exception:
        return None


def _week_start_iso(day_str: str) -> str:
    try:
        day_value = date.fromisoformat(str(day_str))
        return (day_value - timedelta(days=day_value.weekday())).isoformat()
    except Exception:
        return ""


def _use_gsheet_backend() -> bool:
    return str(_get_setting("BID_LOG_BACKEND", "") or "").strip().lower() == GSHEET_BACKEND_NAME


def _use_gist_backend() -> bool:
    return str(_get_setting("BID_LOG_BACKEND", "") or "").strip().lower() == GIST_BACKEND_NAME


def _get_setting(name: str, default: Any = None) -> Any:
    value = os.getenv(name)
    if value not in (None, ""):
        return value
    try:
        import streamlit as st  # type: ignore

        if hasattr(st, "secrets") and name in st.secrets:
            return st.secrets[name]
    except Exception:
        pass
    return default


def _get_gsheet_ws():
    try:
        import gspread
        from google.oauth2.service_account import Credentials
    except Exception as exc:
        raise RuntimeError("Google Sheets dependencies are not installed") from exc

    sheet_id = str(_get_setting("BID_GSHEET_ID", "") or "").strip()
    worksheet_name = str(_get_setting("BID_GSHEET_WORKSHEET", "bid_changes") or "bid_changes").strip()
    sa_json_raw = _get_setting("BID_GSHEETS_SERVICE_ACCOUNT_JSON")
    if not sheet_id or not sa_json_raw:
        raise RuntimeError("Google Sheets bid log settings are missing")

    sa_info = dict(sa_json_raw) if isinstance(sa_json_raw, dict) else json.loads(str(sa_json_raw))
    creds = Credentials.from_service_account_info(sa_info, scopes=["https://www.googleapis.com/auth/spreadsheets"])
    client = gspread.authorize(creds)
    sheet = client.open_by_key(sheet_id)
    try:
        return sheet.worksheet(worksheet_name)
    except Exception:
        return sheet.add_worksheet(title=worksheet_name, rows=1000, cols=max(10, len(BID_LOG_COLUMNS)))


def _ensure_gsheet_log() -> None:
    worksheet = _get_gsheet_ws()
    if worksheet.row_values(1) != BID_LOG_COLUMNS:
        worksheet.clear()
        worksheet.append_row(BID_LOG_COLUMNS, value_input_option="RAW")


def _append_gsheet_row(payload: dict[str, Any]) -> None:
    worksheet = _get_gsheet_ws()
    if worksheet.row_values(1) != BID_LOG_COLUMNS:
        _ensure_gsheet_log()
        worksheet = _get_gsheet_ws()
    worksheet.append_row([payload.get(column, "") for column in BID_LOG_COLUMNS], value_input_option="USER_ENTERED")


def _load_gsheet_rows() -> pd.DataFrame:
    worksheet = _get_gsheet_ws()
    values = worksheet.get_all_values()
    if not values or len(values) <= 1:
        return pd.DataFrame(columns=BID_LOG_COLUMNS)
    return pd.DataFrame(values[1:], columns=values[0])


def _get_gist_config() -> tuple[str, str, str]:
    gist_id = str(_get_setting("BID_GIST_ID", "") or "").strip()
    token = str(_get_setting("BID_GIST_TOKEN", _get_setting("GITHUB_TOKEN", "")) or "").strip()
    filename = str(_get_setting("BID_GIST_FILENAME", "bid_changes.json") or "bid_changes.json").strip()
    if not gist_id or not token:
        raise RuntimeError("Gist bid log settings are missing")
    return gist_id, token, filename


def _gist_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"token {token}", "Accept": "application/vnd.github+json"}


def _load_gist_payload() -> tuple[list[dict[str, Any]], str]:
    gist_id, token, filename = _get_gist_config()
    resp = requests.get(f"https://api.github.com/gists/{gist_id}", headers=_gist_headers(token), timeout=30)
    resp.raise_for_status()
    files = (resp.json().get("files", {}) or {})
    file_obj = files.get(filename)
    if not file_obj:
        return [], filename
    content = str(file_obj.get("content", "") or "").strip()
    if not content:
        return [], filename
    parsed = json.loads(content)
    return (parsed if isinstance(parsed, list) else []), filename


def _save_gist_payload(rows: list[dict[str, Any]], filename: str) -> None:
    gist_id, token, _ = _get_gist_config()
    payload = {"files": {filename: {"content": json.dumps(rows, ensure_ascii=False, indent=2)}}}
    resp = requests.patch(
        f"https://api.github.com/gists/{gist_id}",
        headers=_gist_headers(token),
        json=payload,
        timeout=30,
    )
    resp.raise_for_status()


def _append_gist_row(payload: dict[str, Any]) -> None:
    rows, filename = _load_gist_payload()
    rows.append({column: str(payload.get(column, "")) for column in BID_LOG_COLUMNS})
    _save_gist_payload(rows, filename)


def _load_gist_rows() -> pd.DataFrame:
    rows, _filename = _load_gist_payload()
    if not rows:
        return pd.DataFrame(columns=BID_LOG_COLUMNS)
    return pd.DataFrame(rows)
