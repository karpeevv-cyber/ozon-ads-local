# -*- coding: utf-8 -*-
from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path
import os
import pickle
import json

import pandas as pd


def load_ui_state_cache(path: str) -> dict:
    p = Path(path)
    if not p.exists():
        return {}
    try:
        with p.open("rb") as f:
            return pickle.load(f) or {}
    except Exception:
        return {}


def save_ui_state_cache(state: dict, path: str) -> None:
    if not state:
        return
    try:
        with Path(path).open("wb") as f:
            pickle.dump(state, f)
    except Exception:
        return


def make_ui_state_cache_key(selected_company: str | None, date_from: str | None, date_to: str | None) -> str:
    return f"{selected_company}|{date_from}|{date_to}"


def normalize_ui_state_cache(cache: dict) -> dict:
    if not isinstance(cache, dict):
        return {"entries": {}}
    entries = cache.get("entries")
    if isinstance(entries, dict):
        return cache
    legacy = {}
    for k in ("rows_csv", "daily_rows", "date_from", "date_to", "selected_company"):
        if k in cache:
            legacy = cache
            break
    normalized = {"entries": {}}
    if legacy:
        key = make_ui_state_cache_key(
            legacy.get("selected_company"),
            legacy.get("date_from"),
            legacy.get("date_to"),
        )
        normalized["entries"][key] = legacy
        if legacy.get("selected_company"):
            normalized["selected_company"] = legacy.get("selected_company")
    return normalized


def get_ui_state_entry(cache: dict, key: str) -> dict | None:
    if not isinstance(cache, dict):
        return None
    entries = cache.get("entries")
    if not isinstance(entries, dict):
        return None
    return entries.get(key)


def save_ui_state_entry(path: str, key: str, entry: dict, selected_company: str | None = None) -> None:
    cache = normalize_ui_state_cache(load_ui_state_cache(path))
    entries = cache.setdefault("entries", {})
    entries[key] = entry
    if selected_company:
        cache["selected_company"] = selected_company
    if entry.get("date_from"):
        cache["date_from"] = entry.get("date_from")
    if entry.get("date_to"):
        cache["date_to"] = entry.get("date_to")
    save_ui_state_cache(cache, path)


def load_campaign_reco_map(path: str) -> dict:
    if not os.path.exists(path):
        return {}
    try:
        df = pd.read_csv(path)
        if "campaign_id" not in df.columns or "recommended_strategy" not in df.columns:
            return {}
        return dict(zip(df["campaign_id"].astype(str), df["recommended_strategy"].astype(str)))
    except Exception:
        return {}


def save_campaign_reco_map(path: str, reco_map: dict) -> None:
    if not reco_map:
        return
    try:
        df = pd.DataFrame(
            [{"campaign_id": str(k), "recommended_strategy": str(v)} for k, v in reco_map.items()]
        )
        df.to_csv(path, index=False)
    except Exception:
        return


def _normalize_comments_df(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame(columns=["ts", "day", "week", "company", "campaign_id", "comment"])
    df = df.copy()
    for col in ["ts", "day", "week", "company", "campaign_id", "comment"]:
        if col not in df.columns:
            df[col] = ""
    missing_day = df["day"].isna() | (df["day"].astype(str).str.strip() == "")
    if missing_day.any():
        ts = pd.to_datetime(df["ts"], errors="coerce")
        df.loc[missing_day, "day"] = ts.dt.date.astype(str)
    missing_week = df["week"].isna() | (df["week"].astype(str).str.strip() == "")
    if missing_week.any():
        def _week_start(day_str: str) -> str:
            try:
                d = datetime.fromisoformat(str(day_str)).date()
                return (d - timedelta(days=d.weekday())).isoformat()
            except Exception:
                return ""

        df.loc[missing_week, "week"] = df.loc[missing_week, "day"].apply(_week_start)
    df["campaign_id"] = df["campaign_id"].astype(str)
    df["company"] = df["company"].astype(str)
    df["comment"] = df["comment"].astype(str)
    return df[["ts", "day", "week", "company", "campaign_id", "comment"]]


def load_campaign_comments(path: str) -> pd.DataFrame:
    if not os.path.exists(path):
        return pd.DataFrame(columns=["ts", "day", "week", "company", "campaign_id", "comment"])
    try:
        df = pd.read_csv(path)
    except Exception:
        return pd.DataFrame(columns=["ts", "day", "week", "company", "campaign_id", "comment"])
    return _normalize_comments_df(df)


def append_campaign_comment(
    path: str,
    campaign_id: str,
    comment: str,
    day: date | None = None,
    company: str | None = None,
) -> None:
    if not comment:
        return
    now = datetime.now()
    day_value = day or now.date()
    day_str = day_value.isoformat()
    week_start = (day_value - timedelta(days=day_value.weekday())).isoformat()
    new_row = {
        "ts": now.isoformat(timespec="seconds"),
        "day": day_str,
        "week": week_start,
        "company": str(company or "").strip(),
        "campaign_id": str(campaign_id),
        "comment": str(comment).strip(),
    }
    df = load_campaign_comments(path)
    df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
    df.to_csv(path, index=False)


def default_company_from_env() -> dict:
    return {
        "perf_client_id": os.getenv("PERF_CLIENT_ID", ""),
        "perf_client_secret": os.getenv("PERF_CLIENT_SECRET", ""),
        "seller_client_id": os.getenv("SELLER_CLIENT_ID", ""),
        "seller_api_key": os.getenv("SELLER_API_KEY", ""),
    }


def _parse_company_value(value: str) -> dict:
    raw = value.strip().strip("\"'").strip()
    if not raw:
        return {}
    if raw.startswith("{"):
        try:
            data = json.loads(raw)
        except Exception:
            data = {}
        if isinstance(data, dict):
            return {str(k).strip().lower(): str(v).strip() for k, v in data.items()}
        return {}
    # split by ; or , or |
    parts = []
    for sep in [";", "|", ","]:
        if sep in raw:
            parts = [p for p in raw.split(sep) if p.strip()]
            break
    if not parts:
        parts = [raw]
    out = {}
    for p in parts:
        if "=" not in p:
            continue
        k, v = p.split("=", 1)
        out[k.strip().lower()] = v.strip().strip("\"'")
    return out


def _normalize_company_fields(data: dict) -> dict:
    mapping = {
        "perf_client_id": "perf_client_id",
        "perf_client_secret": "perf_client_secret",
        "seller_client_id": "seller_client_id",
        "seller_api_key": "seller_api_key",
        "perf_clientid": "perf_client_id",
        "perf_clientsecret": "perf_client_secret",
        "seller_clientid": "seller_client_id",
        "seller_apikey": "seller_api_key",
    }
    out = {"perf_client_id": "", "perf_client_secret": "", "seller_client_id": "", "seller_api_key": ""}
    for k, v in data.items():
        key = mapping.get(str(k).strip().lower())
        if key:
            out[key] = str(v).strip()
    return out


def load_company_configs(env_path: str = ".env") -> dict[str, dict]:
    configs: dict[str, dict] = {}

    # 1) Parse block-style companies:
    # company: Name
    # PERF_CLIENT_ID=...
    # PERF_CLIENT_SECRET=...
    # SELLER_CLIENT_ID=...
    # SELLER_API_KEY=...
    try:
        raw = Path(env_path).read_text(encoding="utf-8")
    except Exception:
        raw = ""
    current_name = ""
    current_data: dict = {}
    for line in raw.splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        if s.lower().startswith("company:"):
            if current_name and any(current_data.values()):
                configs[current_name] = _normalize_company_fields(current_data)
            current_name = s.split(":", 1)[1].strip()
            current_data = {}
            continue
        if current_name and "=" in s:
            k, v = s.split("=", 1)
            current_data[k.strip()] = v.strip()
            continue
    if current_name and any(current_data.values()):
        configs[current_name] = _normalize_company_fields(current_data)

    # 2) Parse explicit company lines in .env (single-line)
    for line in raw.splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        if not s.lower().startswith("company"):
            continue
        key, sep, value = s.partition("=")
        if not sep:
            continue
        name = key[len("company"):].lstrip("_- .")
        name = name if name else key
        data = _parse_company_value(value)
        norm = _normalize_company_fields(data)
        if any(norm.values()):
            configs[name] = norm

    # 3) Parse grouped env vars like company_<name>_PERF_CLIENT_ID
    for env_key, env_value in os.environ.items():
        k = env_key.strip()
        if not k.lower().startswith("company_"):
            continue
        rest = k[len("company_") :]
        if "_" not in rest:
            continue
        name, _, field = rest.partition("_")
        norm = _normalize_company_fields({field.lower(): env_value})
        if name:
            current = configs.get(name, {"perf_client_id": "", "perf_client_secret": "", "seller_client_id": "", "seller_api_key": ""})
            for fk, fv in norm.items():
                if fv:
                    current[fk] = fv
            configs[name] = current

    return configs
