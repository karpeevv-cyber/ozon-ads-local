from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
from app.services.bid_history import load_bid_changes, load_campaign_comments_from_bid_log
from app.services.storage_paths import backend_data_path, legacy_root_path


def _bid_changes_path() -> Path:
    return backend_data_path("bid_changes.csv")


def _legacy_bid_changes_path() -> Path:
    return legacy_root_path("bid_changes.csv")


def _campaign_comments_path() -> Path:
    return backend_data_path("campaign_comments.csv")


def _legacy_campaign_comments_path() -> Path:
    return legacy_root_path("campaign_comments.csv")


def load_bid_changes_df(path: str = "bid_changes.csv") -> pd.DataFrame:
    if path != "bid_changes.csv":
        return load_bid_changes(path=str(Path(path).resolve()))

    frames: list[pd.DataFrame] = []
    for resolved in [_bid_changes_path(), _legacy_bid_changes_path()]:
        if not resolved.exists():
            continue
        try:
            frame = load_bid_changes(path=str(resolved))
        except Exception:
            continue
        if frame is not None and not frame.empty:
            frames.append(frame)
    if not frames:
        return load_bid_changes(path=str(_bid_changes_path()))
    combined = pd.concat(frames, ignore_index=True)
    combined = combined.drop_duplicates(
        subset=["ts_iso", "date", "campaign_id", "sku", "old_bid_micro", "new_bid_micro", "reason", "comment"],
        keep="first",
    )
    return combined


def _normalize_comments_df(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame(columns=["ts", "day", "week", "company", "campaign_id", "comment"])
    out = df.copy()
    for col in ["ts", "day", "week", "company", "campaign_id", "comment"]:
        if col not in out.columns:
            out[col] = ""
    missing_day = out["day"].isna() | (out["day"].astype(str).str.strip() == "")
    if missing_day.any():
        ts = pd.to_datetime(out["ts"], errors="coerce")
        out.loc[missing_day, "day"] = ts.dt.date.astype(str)
    missing_week = out["week"].isna() | (out["week"].astype(str).str.strip() == "")
    if missing_week.any():
        def week_start(day_str: str) -> str:
            try:
                day = datetime.fromisoformat(str(day_str)).date()
                return (day - timedelta(days=day.weekday())).isoformat()
            except Exception:
                return ""

        out.loc[missing_week, "week"] = out.loc[missing_week, "day"].apply(week_start)
    out["campaign_id"] = out["campaign_id"].astype(str)
    out["company"] = out["company"].astype(str).apply(_normalize_legacy_company_name)
    out["comment"] = out["comment"].astype(str)
    return out[["ts", "day", "week", "company", "campaign_id", "comment"]]


def _normalize_legacy_company_name(value: str) -> str:
    text = str(value or "").strip()
    normalized = text.lower().replace("_", " ")
    aliases = {
        "osome": "osome",
        "osome tea": "osome",
        "osomo": "osome",
        "aura": "aura",
        "aura tea": "aura",
    }
    return aliases.get(normalized, text)


def load_campaign_comments_df(path: str = "campaign_comments.csv") -> pd.DataFrame:
    if path != "campaign_comments.csv":
        shared_df = _normalize_comments_df(load_campaign_comments_from_bid_log(path=str(_bid_changes_path())))
        resolved = Path(path).resolve()
        if not resolved.exists():
            return shared_df
        try:
            local_df = pd.read_csv(resolved)
        except Exception:
            return shared_df
        local_df = _normalize_comments_df(local_df)
        if shared_df.empty:
            return local_df
        if local_df.empty:
            return shared_df
        combined = pd.concat([shared_df, local_df], ignore_index=True)
        combined = combined.drop_duplicates(
            subset=["ts", "day", "week", "company", "campaign_id", "comment"],
            keep="first",
        )
        return _normalize_comments_df(combined)

    frames: list[pd.DataFrame] = []
    for bid_path in [_bid_changes_path(), _legacy_bid_changes_path()]:
        try:
            frame = _normalize_comments_df(load_campaign_comments_from_bid_log(path=str(bid_path)))
        except Exception:
            frame = pd.DataFrame()
        if frame is not None and not frame.empty:
            frames.append(frame)
    for comments_path in [_campaign_comments_path(), _legacy_campaign_comments_path()]:
        if not comments_path.exists():
            continue
        try:
            frame = pd.read_csv(comments_path)
        except Exception:
            continue
        frame = _normalize_comments_df(frame)
        if not frame.empty:
            frames.append(frame)
    if not frames:
        return pd.DataFrame(columns=["ts", "day", "week", "company", "campaign_id", "comment"])
    combined = pd.concat(frames, ignore_index=True)
    combined = combined.drop_duplicates(
        subset=["ts", "day", "week", "company", "campaign_id", "comment"],
        keep="first",
    )
    return _normalize_comments_df(combined)
