# -*- coding: utf-8 -*-
from __future__ import annotations

from datetime import datetime
from pathlib import Path
import pandas as pd


DEFAULT_PATH = "strategy_map.csv"


def _ensure_df(df: pd.DataFrame) -> pd.DataFrame:
    cols = ["campaign_id", "sku", "strategy_id", "updated_at", "notes"]
    for c in cols:
        if c not in df.columns:
            df[c] = ""
    return df[cols]


def load_strategy_map(path: str = DEFAULT_PATH) -> pd.DataFrame:
    p = Path(path)
    if not p.exists():
        return _ensure_df(pd.DataFrame())
    try:
        df = pd.read_csv(p, dtype=str).fillna("")
    except Exception:
        return _ensure_df(pd.DataFrame())
    return _ensure_df(df)


def get_strategy(campaign_id: str, sku: str, path: str = DEFAULT_PATH) -> str | None:
    df = load_strategy_map(path)
    if df.empty:
        return None
    row = df[(df["campaign_id"] == str(campaign_id)) & (df["sku"] == str(sku))]
    if row.empty:
        return None
    val = str(row.iloc[0].get("strategy_id", "")).strip()
    return val or None


def upsert_strategy(
    campaign_id: str,
    sku: str,
    strategy_id: str,
    notes: str = "",
    path: str = DEFAULT_PATH,
):
    df = load_strategy_map(path)
    mask = (df["campaign_id"] == str(campaign_id)) & (df["sku"] == str(sku))
    now = datetime.utcnow().isoformat(timespec="seconds") + "Z"
    if mask.any():
        df.loc[mask, "strategy_id"] = str(strategy_id)
        df.loc[mask, "updated_at"] = now
        df.loc[mask, "notes"] = notes
    else:
        df = pd.concat(
            [
                df,
                pd.DataFrame(
                    [
                        {
                            "campaign_id": str(campaign_id),
                            "sku": str(sku),
                            "strategy_id": str(strategy_id),
                            "updated_at": now,
                            "notes": notes,
                        }
                    ]
                ),
            ],
            ignore_index=True,
        )
    Path(path).write_text(df.to_csv(index=False), encoding="utf-8")
