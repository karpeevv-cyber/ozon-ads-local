# bid_changes.py
from __future__ import annotations

import csv
import json
import os
from dataclasses import dataclass
from datetime import datetime, date
from typing import Optional, Any
from zoneinfo import ZoneInfo

import pandas as pd
import requests

BID_LOG_PATH_DEFAULT = "bid_changes.csv"
TZ_DEFAULT = ZoneInfo("Europe/Moscow")
GSHEET_BACKEND_NAME = "gsheets"
GIST_BACKEND_NAME = "gist"

BID_LOG_COLUMNS = [
    "ts_iso",         # 2026-01-28T14:32:10+03:00
    "date",           # 2026-01-28
    "campaign_id",
    "sku",
    "old_bid_micro",  # int or empty
    "new_bid_micro",  # int
    "reason",         # "test" | "manual change"
    "comment",        # free text
]


@dataclass(frozen=True)
class BidChange:
    ts_iso: str
    date: str
    campaign_id: str
    sku: str
    old_bid_micro: Optional[int]
    new_bid_micro: int
    reason: str
    comment: str


def ensure_bid_log(path: str = BID_LOG_PATH_DEFAULT) -> None:
    if _use_gist_backend():
        return
    if _use_gsheet_backend():
        try:
            _ensure_gsheet_log()
            return
        except Exception:
            # Fall back to local CSV if Sheets backend is not configured/available.
            pass
    if os.path.exists(path):
        return
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=BID_LOG_COLUMNS, delimiter=";")
        writer.writeheader()


def rub_to_micro(rub_value: float) -> int:
    return int(round(float(rub_value) * 1_000_000))


def micro_to_rub_value(micro: Optional[int]) -> Optional[float]:
    if micro is None:
        return None
    try:
        return float(micro) / 1_000_000
    except Exception:
        return None


def append_bid_change(
    *,
    campaign_id: str,
    sku: str,
    old_bid_micro: Optional[int],
    new_bid_micro: int,
    reason: str,
    comment: str = "",
    path: str = BID_LOG_PATH_DEFAULT,
    tz: ZoneInfo = TZ_DEFAULT,
) -> BidChange:
    ensure_bid_log(path)

    now = datetime.now(tz)
    row = BidChange(
        ts_iso=now.isoformat(),
        date=now.date().isoformat(),
        campaign_id=str(campaign_id),
        sku=str(sku),
        old_bid_micro=_to_int_or_none(old_bid_micro),
        new_bid_micro=int(new_bid_micro),
        reason=str(reason),
        comment=str(comment),
    )

    payload = {
        "ts_iso": row.ts_iso,
        "date": row.date,
        "campaign_id": row.campaign_id,
        "sku": row.sku,
        "old_bid_micro": "" if row.old_bid_micro is None else str(row.old_bid_micro),
        "new_bid_micro": str(row.new_bid_micro),
        "reason": row.reason,
        "comment": row.comment,
    }
    if _use_gsheet_backend():
        try:
            _append_gsheet_row(payload)
            return row
        except Exception:
            # If Sheets write fails, keep local logging to avoid data loss.
            pass
    if _use_gist_backend():
        try:
            _append_gist_row(payload)
            return row
        except Exception:
            # If Gist write fails, keep local logging to avoid data loss.
            pass

    with open(path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=BID_LOG_COLUMNS, delimiter=";")
        writer.writerow(payload)

    return row


def load_bid_changes(path: str = BID_LOG_PATH_DEFAULT) -> pd.DataFrame:
    if _use_gist_backend():
        try:
            df = _load_gist_rows()
            if not df.empty:
                for c in BID_LOG_COLUMNS:
                    if c not in df.columns:
                        df[c] = ""
                df = df[BID_LOG_COLUMNS].copy()
                df["old_bid_micro"] = df["old_bid_micro"].apply(_to_int_or_none).astype("Int64")
                df["new_bid_micro"] = df["new_bid_micro"].apply(_to_int_or_none).astype("Int64")
                return df
        except Exception:
            # If Gist is unavailable, fall back to local CSV.
            pass
    if _use_gsheet_backend():
        try:
            df = _load_gsheet_rows()
            if not df.empty:
                for c in BID_LOG_COLUMNS:
                    if c not in df.columns:
                        df[c] = ""
                df = df[BID_LOG_COLUMNS].copy()
                df["old_bid_micro"] = df["old_bid_micro"].apply(_to_int_or_none).astype("Int64")
                df["new_bid_micro"] = df["new_bid_micro"].apply(_to_int_or_none).astype("Int64")
                return df
        except Exception:
            # If Sheets is unavailable, fall back to local CSV.
            pass

    if not os.path.exists(path):
        return pd.DataFrame(columns=BID_LOG_COLUMNS)

    df = pd.read_csv(path, sep=";", encoding="utf-8", dtype=str).fillna("")

    for c in BID_LOG_COLUMNS:
        if c not in df.columns:
            df[c] = ""

    df["old_bid_micro"] = df["old_bid_micro"].apply(_to_int_or_none).astype("Int64")
    df["new_bid_micro"] = df["new_bid_micro"].apply(_to_int_or_none).astype("Int64")

    return df[BID_LOG_COLUMNS].copy()


def get_last_set_bid_micro(
    df: pd.DataFrame,
    *,
    campaign_id: str,
    sku: str,
) -> Optional[int]:
    if df is None or df.empty:
        return None

    sub = df[
        (df["campaign_id"].astype(str) == str(campaign_id))
        & (df["sku"].astype(str) == str(sku))
    ]
    if sub.empty:
        return None

    sub = sub.sort_values("ts_iso")
    v = sub.iloc[-1]["new_bid_micro"]
    try:
        if pd.isna(v):
            return None
        return int(v)
    except Exception:
        return None


def format_changes_for_day(
    df: pd.DataFrame,
    *,
    campaign_id: str,
    sku: str,
    day_iso: str,  # YYYY-MM-DD
) -> str:
    rows = _filter_rows(df, campaign_id=campaign_id, sku=sku)
    if rows.empty:
        return ""

    rows = rows[rows["date"].astype(str) == str(day_iso)]
    if rows.empty:
        return ""

    rows = rows.sort_values("ts_iso")
    parts: list[str] = []
    for _, r in rows.iterrows():
        parts.append(_format_one_change(r))
    return "; ".join(parts)


def format_changes_for_week(
    df: pd.DataFrame,
    *,
    campaign_id: str,
    sku: str,
    week_start_iso: str,  # YYYY-MM-DD (week start)
) -> str:
    rows = _filter_rows(df, campaign_id=campaign_id, sku=sku)
    if rows.empty:
        return ""

    try:
        ws = date.fromisoformat(str(week_start_iso))
    except Exception:
        return ""

    we = ws.toordinal() + 6

    def _in_week(d: str) -> bool:
        try:
            di = date.fromisoformat(str(d)).toordinal()
            return ws.toordinal() <= di <= we
        except Exception:
            return False

    rows = rows[rows["date"].apply(_in_week)]
    if rows.empty:
        return ""

    rows = rows.sort_values("ts_iso")
    parts: list[str] = []
    for _, r in rows.iterrows():
        parts.append(_format_one_change(r))
    return "; ".join(parts)


def format_changes_for_day_with_comment(
    df: pd.DataFrame,
    *,
    campaign_id: str,
    sku: str,
    day_iso: str,  # YYYY-MM-DD
) -> tuple[str, str]:
    rows = _filter_rows(df, campaign_id=campaign_id, sku=sku)
    if rows.empty:
        return ("", "")

    rows = rows[rows["date"].astype(str) == str(day_iso)]
    if rows.empty:
        return ("", "")

    rows = rows.sort_values("ts_iso")
    parts: list[str] = []
    comments: list[str] = []
    for _, r in rows.iterrows():
        parts.append(_format_one_change(r))
        c = str(r.get("comment", "")).strip()
        if c:
            comments.append(f"{r.get('date','')}: {c}")
    return ("; ".join(parts), "; ".join(comments))


def format_changes_for_day_with_comment_compact(
    df: pd.DataFrame,
    *,
    campaign_id: str,
    sku: str,
    day_iso: str,  # YYYY-MM-DD
) -> tuple[str, str]:
    """
    Like format_changes_for_day_with_comment, but without date/reason in change text
    and without date prefix in comments.
    """
    rows = _filter_rows(df, campaign_id=campaign_id, sku=sku)
    if rows.empty:
        return ("", "")

    rows = rows[rows["date"].astype(str) == str(day_iso)]
    if rows.empty:
        return ("", "")

    rows = rows.sort_values("ts_iso")
    parts: list[str] = []
    comments: list[str] = []
    for _, r in rows.iterrows():
        parts.append(_format_one_change_compact(r))
        c = str(r.get("comment", "")).strip()
        if c:
            comments.append(c)
    return ("; ".join(parts), "; ".join(comments))


def format_changes_for_week_with_comment(
    df: pd.DataFrame,
    *,
    campaign_id: str,
    sku: str,
    week_start_iso: str,  # YYYY-MM-DD (week start)
) -> tuple[str, str]:
    rows = _filter_rows(df, campaign_id=campaign_id, sku=sku)
    if rows.empty:
        return ("", "")

    try:
        ws = date.fromisoformat(str(week_start_iso))
    except Exception:
        return ("", "")

    we = ws.toordinal() + 6

    def _in_week(d: str) -> bool:
        try:
            di = date.fromisoformat(str(d)).toordinal()
            return ws.toordinal() <= di <= we
        except Exception:
            return False

    rows = rows[rows["date"].apply(_in_week)]
    if rows.empty:
        return ("", "")

    rows = rows.sort_values("ts_iso")
    parts: list[str] = []
    comments: list[str] = []
    for _, r in rows.iterrows():
        parts.append(_format_one_change(r))
        c = str(r.get("comment", "")).strip()
        if c:
            comments.append(f"{r.get('date','')}: {c}")
    return ("; ".join(parts), "; ".join(comments))


# ---------------- internal helpers ----------------

def _to_int_or_none(x) -> Optional[int]:
    if x is None:
        return None
    if isinstance(x, int):
        return int(x)
    s = str(x).strip()
    if not s or s.lower() in {"nan", "none", "<na>"}:
        return None
    try:
        return int(float(s.replace(" ", "").replace(",", ".")))
    except Exception:
        return None


def _filter_rows(df: pd.DataFrame, *, campaign_id: str, sku: str) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    return df[
        (df["campaign_id"].astype(str) == str(campaign_id))
        & (df["sku"].astype(str) == str(sku))
    ].copy()


def _fmt_rub_value(micro: Optional[int]) -> str:
    v = micro_to_rub_value(micro)
    if v is None:
        return "n/a"
    if float(v).is_integer():
        return str(int(v))
    return f"{v:.2f}".rstrip("0").rstrip(".")


def _format_one_change(row) -> str:
    d = str(row.get("date", "")).strip()
    old_micro = _to_int_or_none(row.get("old_bid_micro"))
    new_micro = _to_int_or_none(row.get("new_bid_micro"))
    reason = str(row.get("reason", "")).strip()
    return f"{d}: {_fmt_rub_value(old_micro)} -> {_fmt_rub_value(new_micro)}, reason={reason}"


def _format_one_change_compact(row) -> str:
    old_micro = _to_int_or_none(row.get("old_bid_micro"))
    new_micro = _to_int_or_none(row.get("new_bid_micro"))
    return f"{_fmt_rub_value(old_micro)} -> {_fmt_rub_value(new_micro)}"


def _use_gsheet_backend() -> bool:
    backend = str(_get_setting("BID_LOG_BACKEND", "") or "").strip().lower()
    return backend == GSHEET_BACKEND_NAME


def _use_gist_backend() -> bool:
    backend = str(_get_setting("BID_LOG_BACKEND", "") or "").strip().lower()
    return backend == GIST_BACKEND_NAME


def _get_setting(name: str, default: Any = None) -> Any:
    val = os.getenv(name)
    if val not in (None, ""):
        return val
    try:
        import streamlit as st  # lazy import to keep non-UI usage working

        if hasattr(st, "secrets") and name in st.secrets:
            return st.secrets[name]
    except Exception:
        pass
    return default


def _get_gsheet_config() -> tuple[str, str, dict[str, Any]]:
    sheet_id = str(_get_setting("BID_GSHEET_ID", "") or "").strip()
    worksheet = str(_get_setting("BID_GSHEET_WORKSHEET", "bid_changes") or "bid_changes").strip()
    sa_json_raw = _get_setting("BID_GSHEETS_SERVICE_ACCOUNT_JSON")

    if not sheet_id:
        raise RuntimeError("BID_GSHEET_ID is missing")
    if not sa_json_raw:
        raise RuntimeError("BID_GSHEETS_SERVICE_ACCOUNT_JSON is missing")

    if isinstance(sa_json_raw, dict):
        sa_info = dict(sa_json_raw)
    else:
        sa_info = json.loads(str(sa_json_raw))
    return sheet_id, worksheet, sa_info


def _get_gsheet_ws():
    try:
        import gspread
        from google.oauth2.service_account import Credentials
    except Exception as e:
        raise RuntimeError("Google Sheets dependencies are not installed") from e

    sheet_id, worksheet_name, sa_info = _get_gsheet_config()
    scopes = ["https://www.googleapis.com/auth/spreadsheets"]
    creds = Credentials.from_service_account_info(sa_info, scopes=scopes)
    client = gspread.authorize(creds)
    sh = client.open_by_key(sheet_id)
    try:
        ws = sh.worksheet(worksheet_name)
    except Exception:
        ws = sh.add_worksheet(title=worksheet_name, rows=1000, cols=max(10, len(BID_LOG_COLUMNS)))
    return ws


def _ensure_gsheet_log() -> None:
    ws = _get_gsheet_ws()
    first_row = ws.row_values(1)
    if first_row != BID_LOG_COLUMNS:
        ws.clear()
        ws.append_row(BID_LOG_COLUMNS, value_input_option="RAW")


def _append_gsheet_row(payload: dict[str, Any]) -> None:
    ws = _get_gsheet_ws()
    if ws.row_values(1) != BID_LOG_COLUMNS:
        _ensure_gsheet_log()
        ws = _get_gsheet_ws()
    ws.append_row([payload.get(c, "") for c in BID_LOG_COLUMNS], value_input_option="USER_ENTERED")


def _load_gsheet_rows() -> pd.DataFrame:
    ws = _get_gsheet_ws()
    values = ws.get_all_values()
    if not values or len(values) <= 1:
        return pd.DataFrame(columns=BID_LOG_COLUMNS)
    header = values[0]
    rows = values[1:]
    df = pd.DataFrame(rows, columns=header)
    return df


def _get_gist_config() -> tuple[str, str, str]:
    gist_id = str(_get_setting("BID_GIST_ID", "") or "").strip()
    token = str(_get_setting("BID_GIST_TOKEN", _get_setting("GITHUB_TOKEN", "")) or "").strip()
    filename = str(_get_setting("BID_GIST_FILENAME", "bid_changes.json") or "bid_changes.json").strip()
    if not gist_id:
        raise RuntimeError("BID_GIST_ID is missing")
    if not token:
        raise RuntimeError("BID_GIST_TOKEN (or GITHUB_TOKEN) is missing")
    return gist_id, token, filename


def _gist_headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github+json",
    }


def _load_gist_payload() -> tuple[list[dict[str, Any]], str]:
    gist_id, token, filename = _get_gist_config()
    url = f"https://api.github.com/gists/{gist_id}"
    resp = requests.get(url, headers=_gist_headers(token), timeout=30)
    resp.raise_for_status()
    data = resp.json()
    files = data.get("files", {}) or {}
    file_obj = files.get(filename)
    if not file_obj:
        return ([], filename)
    content = str(file_obj.get("content", "") or "").strip()
    if not content:
        return ([], filename)
    parsed = json.loads(content)
    if isinstance(parsed, list):
        return (parsed, filename)
    return ([], filename)


def _save_gist_payload(rows: list[dict[str, Any]], filename: str) -> None:
    gist_id, token, _ = _get_gist_config()
    url = f"https://api.github.com/gists/{gist_id}"
    payload = {
        "files": {
            filename: {
                "content": json.dumps(rows, ensure_ascii=False, indent=2),
            }
        }
    }
    resp = requests.patch(url, headers=_gist_headers(token), json=payload, timeout=30)
    resp.raise_for_status()


def _append_gist_row(payload: dict[str, Any]) -> None:
    rows, filename = _load_gist_payload()
    rows.append({c: str(payload.get(c, "")) for c in BID_LOG_COLUMNS})
    _save_gist_payload(rows, filename)


def _load_gist_rows() -> pd.DataFrame:
    rows, _filename = _load_gist_payload()
    if not rows:
        return pd.DataFrame(columns=BID_LOG_COLUMNS)
    return pd.DataFrame(rows)
