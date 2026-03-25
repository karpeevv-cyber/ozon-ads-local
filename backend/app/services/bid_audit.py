from __future__ import annotations

import pandas as pd

from app.services.bid_log import load_bid_changes_df, load_campaign_comments_df

def get_recent_bid_changes(*, company: str | None = None, limit: int = 20) -> list[dict]:
    df = load_bid_changes_df()
    if df is None or df.empty:
        return []
    out = df.copy()
    if company and "reason" in out.columns:
        pass
    out = out.sort_values("ts_iso", ascending=False).head(limit)
    records: list[dict] = []
    for _, row in out.iterrows():
        records.append(
            {
                "ts_iso": str(row.get("ts_iso", "") or ""),
                "date": str(row.get("date", "") or ""),
                "campaign_id": str(row.get("campaign_id", "") or ""),
                "sku": str(row.get("sku", "") or ""),
                "old_bid_micro": None if pd.isna(row.get("old_bid_micro")) else int(row.get("old_bid_micro")),
                "new_bid_micro": None if pd.isna(row.get("new_bid_micro")) else int(row.get("new_bid_micro")),
                "reason": str(row.get("reason", "") or ""),
                "comment": str(row.get("comment", "") or ""),
            }
        )
    return records


def get_campaign_comments(*, company: str | None = None, campaign_id: str | None = None, limit: int = 20) -> list[dict]:
    df = load_campaign_comments_df()
    if df is None or df.empty:
        return []
    out = df.copy()
    if company and "company" in out.columns:
        out = out[out["company"].astype(str).isin(["", str(company)])].copy()
    if campaign_id:
        out = out[out["campaign_id"].astype(str) == str(campaign_id)].copy()
    out = out.sort_values(["day", "ts"], ascending=[False, False]).head(limit)
    return [
        {
            "ts": str(row.get("ts", "") or ""),
            "day": str(row.get("day", "") or ""),
            "week": str(row.get("week", "") or ""),
            "company": str(row.get("company", "") or ""),
            "campaign_id": str(row.get("campaign_id", "") or ""),
            "comment": str(row.get("comment", "") or ""),
        }
        for _, row in out.iterrows()
    ]


def get_test_entries(*, company: str | None = None, limit: int = 20) -> list[dict]:
    df = load_bid_changes_df()
    if df is None or df.empty or "reason" not in df.columns:
        return []
    out = df[df["reason"].astype(str) == "Test"].copy()
    if out.empty:
        return []
    rows: list[dict] = []
    for _, row in out.sort_values("ts_iso", ascending=False).head(limit).iterrows():
        comment = str(row.get("comment", "") or "")
        rows.append(
            {
                "ts_iso": str(row.get("ts_iso", "") or ""),
                "date": str(row.get("date", "") or ""),
                "campaign_id": str(row.get("campaign_id", "") or ""),
                "sku": str(row.get("sku", "") or ""),
                "reason": str(row.get("reason", "") or ""),
                "comment": comment,
                "company": company or "",
            }
        )
    return rows
