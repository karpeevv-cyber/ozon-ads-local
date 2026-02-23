# bid_changes.py
from __future__ import annotations

import csv
import os
from dataclasses import dataclass
from datetime import datetime, date
from typing import Optional
from zoneinfo import ZoneInfo

import pandas as pd

BID_LOG_PATH_DEFAULT = "bid_changes.csv"
TZ_DEFAULT = ZoneInfo("Europe/Moscow")

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

    with open(path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=BID_LOG_COLUMNS, delimiter=";")
        writer.writerow(
            {
                "ts_iso": row.ts_iso,
                "date": row.date,
                "campaign_id": row.campaign_id,
                "sku": row.sku,
                "old_bid_micro": "" if row.old_bid_micro is None else str(row.old_bid_micro),
                "new_bid_micro": str(row.new_bid_micro),
                "reason": row.reason,
                "comment": row.comment,
            }
        )

    return row


def load_bid_changes(path: str = BID_LOG_PATH_DEFAULT) -> pd.DataFrame:
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

