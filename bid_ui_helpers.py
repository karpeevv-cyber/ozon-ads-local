# bid_ui_helpers.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import pandas as pd

from bid_changes import (
    append_bid_change,
    format_changes_for_day_multiline,
    format_changes_for_range_multiline,
    format_changes_for_week_multiline,
    load_bid_changes,
    rub_to_micro,
)


@dataclass(frozen=True)
class BidApplyResult:
    old_bid_micro: Optional[int]
    new_bid_micro: int
    reason: str


def fetch_old_bid_micro_from_products(products: list[dict], sku: str) -> Optional[int]:
    sku = str(sku)

    for p in products or []:
        if str(p.get("sku")) != sku:
            continue

        raw = p.get("current_bid")
        if raw is None:
            raw = p.get("currentBid")
        if raw is None:
            raw = p.get("bid")

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
    comment: str = "",
    products_loader,        # fn(token, campaign_id) -> list[dict]
    bid_updater,            # fn(token, campaign_id, bids=[{sku,bid}]) -> any
    log_path: str = "bid_changes.csv",
) -> BidApplyResult:
    campaign_id = str(campaign_id)
    sku = str(sku).strip()
    reason = str(reason).strip()

    products = products_loader(token, campaign_id)
    old_bid_micro = fetch_old_bid_micro_from_products(products, sku)

    new_bid_micro = rub_to_micro(bid_rub)

    bid_updater(
        token,
        campaign_id,
        bids=[{"sku": sku, "bid": str(new_bid_micro)}],
    )

    append_bid_change(
        campaign_id=campaign_id,
        sku=sku,
        old_bid_micro=old_bid_micro,
        new_bid_micro=new_bid_micro,
        reason=reason,
        comment=comment,
        path=log_path,
    )

    return BidApplyResult(
        old_bid_micro=old_bid_micro,
        new_bid_micro=new_bid_micro,
        reason=reason,
    )


def load_bid_log_df(log_path: str = "bid_changes.csv") -> pd.DataFrame:
    return load_bid_changes(path=log_path)


def add_bid_columns_daily(
    df_daily: pd.DataFrame,
    *,
    bid_log_df: pd.DataFrame,
    campaign_id: str,
    sku: str,
    day_col: str = "day",
    out_change_col: str = "Bid change",
) -> pd.DataFrame:
    if df_daily is None or df_daily.empty:
        return df_daily

    out = df_daily.copy()
    campaign_id = str(campaign_id)
    sku = str(sku)

    def _fmt(d):
        if not sku:
            return ""
        return format_changes_for_day_multiline(
            bid_log_df,
            campaign_id=campaign_id,
            sku=sku,
            day_iso=str(d),
        )

    if day_col in out.columns:
        out[out_change_col] = out[day_col].astype(str).apply(_fmt)
    else:
        out[out_change_col] = ""

    return out


def add_bid_columns_weekly(
    df_weekly: pd.DataFrame,
    *,
    bid_log_df: pd.DataFrame,
    campaign_id: str,
    sku: str,
    week_col: str = "week",  # YYYY-MM-DD (week start)
    out_change_col: str = "Bid change",
) -> pd.DataFrame:
    if df_weekly is None or df_weekly.empty:
        return df_weekly

    out = df_weekly.copy()
    campaign_id = str(campaign_id)
    sku = str(sku)

    def _fmt(w):
        if not sku:
            return ""
        return format_changes_for_week_multiline(
            bid_log_df,
            campaign_id=campaign_id,
            sku=sku,
            week_start_iso=str(w),
        )

    if week_col in out.columns:
        out[out_change_col] = out[week_col].astype(str).apply(_fmt)
    else:
        out[out_change_col] = ""

    return out


def add_bid_column_period(
    df: pd.DataFrame,
    *,
    bid_log_df: pd.DataFrame,
    date_from: str,
    date_to: str,
    campaign_id_col: str = "campaign_id",
    sku_col: str = "sku",
    out_change_col: str = "Bid change",
) -> pd.DataFrame:
    if df is None or df.empty:
        return df

    out = df.copy()

    def _fmt(row) -> str:
        campaign_id = str(row.get(campaign_id_col, "")).strip()
        sku = str(row.get(sku_col, "")).strip()
        if not campaign_id or not sku or sku in {"", "None", "several", "вЂ”"}:
            return ""
        return format_changes_for_range_multiline(
            bid_log_df,
            campaign_id=campaign_id,
            sku=sku,
            date_from=str(date_from),
            date_to=str(date_to),
        )

    out[out_change_col] = out.apply(_fmt, axis=1)
    return out
