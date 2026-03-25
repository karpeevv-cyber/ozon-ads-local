from __future__ import annotations

from datetime import datetime, timedelta

import pandas as pd

from app.services.bid_log import load_bid_changes_df, load_campaign_comments_df
from app.services.campaign_reporting import compute_daily_breakdown, fetch_ads_daily_totals
from app.services.company_config import resolve_company_config
from app.services.integrations.ozon_ads import get_running_campaigns, perf_token
from app.services.integrations.ozon_seller import seller_analytics_sku_day
from app.services.unit_economics import get_unit_economics_summary


def _to_float(value) -> float:
    try:
        if value is None:
            return 0.0
        if isinstance(value, (int, float)):
            return float(value)
        text = str(value).strip().replace(" ", "").replace(",", ".")
        return float(text) if text else 0.0
    except Exception:
        return 0.0


def _daily_rows_with_legacy_main_logic(
    *,
    company_name: str,
    running_campaigns: list[dict],
    date_from: str,
    date_to: str,
    seller_client_id: str | None,
    seller_api_key: str | None,
    perf_client_id: str | None,
    perf_client_secret: str | None,
    target_drr_pct: float,
) -> pd.DataFrame:
    running_ids = [str(campaign.get("id")) for campaign in running_campaigns if campaign.get("id") is not None]
    if not running_ids:
        return pd.DataFrame()

    _by_sku, by_day, _by_day_sku = seller_analytics_sku_day(
        date_from,
        date_to,
        limit=1000,
        client_id=seller_client_id,
        api_key=seller_api_key,
    )

    token = perf_token(client_id=perf_client_id, client_secret=perf_client_secret)
    ads_daily_rows, _ads_daily_by_campaign = fetch_ads_daily_totals(
        token,
        date_from,
        date_to,
        running_ids,
        15,
        return_by_campaign=True,
    )
    daily_rows = compute_daily_breakdown(ads_daily_rows, by_day, target_drr=float(target_drr_pct) / 100.0)
    df_daily_raw = pd.DataFrame(daily_rows)
    if df_daily_raw.empty:
        return df_daily_raw

    unit_econ_summary = get_unit_economics_summary(company=company_name, date_from=date_from, date_to=date_to)
    ebitda_daily = pd.DataFrame(unit_econ_summary.get("rows", []) or [])
    if not ebitda_daily.empty and "day" in ebitda_daily.columns:
        ebitda_daily = ebitda_daily.rename(columns={"ebitda_total": "ebitda"})
        if "ebitda_pct" not in ebitda_daily.columns:
            ebitda_daily["ebitda_pct"] = ebitda_daily.apply(
                lambda row: (_to_float(row.get("ebitda")) / _to_float(row.get("revenue")) * 100.0)
                if _to_float(row.get("revenue"))
                else 0.0,
                axis=1,
            )
        df_daily_raw = df_daily_raw.merge(
            ebitda_daily[["day", "ebitda", "ebitda_pct"]],
            on="day",
            how="left",
        )

    if "ebitda" not in df_daily_raw.columns:
        df_daily_raw["ebitda"] = 0.0
    if "ebitda_pct" not in df_daily_raw.columns:
        df_daily_raw["ebitda_pct"] = 0.0
    df_daily_raw["ebitda"] = pd.to_numeric(df_daily_raw["ebitda"], errors="coerce").fillna(0.0)
    df_daily_raw["ebitda_pct"] = pd.to_numeric(df_daily_raw["ebitda_pct"], errors="coerce").fillna(0.0)

    campaign_title_map = {
        str(campaign.get("id")): str(campaign.get("title", "") or "").strip()
        for campaign in running_campaigns
        if campaign.get("id") is not None
    }
    campaign_ids_set = set(campaign_title_map.keys())

    bid_changes_day_map: dict[str, int] = {}
    bid_log_df = load_bid_changes_df()
    if bid_log_df is not None and not bid_log_df.empty:
        bid_log_local = bid_log_df.copy()
        bid_log_local["campaign_id"] = bid_log_local["campaign_id"].astype(str)
        bid_log_local = bid_log_local[bid_log_local["campaign_id"].isin(campaign_ids_set)]
        if not bid_log_local.empty:
            bid_log_local["date"] = pd.to_datetime(bid_log_local["date"], errors="coerce")
            bid_log_local = bid_log_local.dropna(subset=["date"])
            if not bid_log_local.empty:
                bid_log_local["date_iso"] = bid_log_local["date"].dt.date.astype(str)
                bid_changes_day_map = {
                    str(key): int(value)
                    for key, value in bid_log_local.groupby("date_iso").size().to_dict().items()
                }

    comments_df = load_campaign_comments_df()
    if comments_df is not None and not comments_df.empty and "day" in df_daily_raw.columns:
        comments_df = comments_df.copy()
        if "company" in comments_df.columns:
            comments_df = comments_df[comments_df["company"].astype(str) == str(company_name)].copy()
        comments_period = comments_df[
            (comments_df["day"].astype(str) >= str(date_from))
            & (comments_df["day"].astype(str) <= str(date_to))
        ].copy()
        if not comments_period.empty:
            comments_period = comments_period.sort_values(["day", "ts"], ascending=[True, False])

            def _merge_day_comments(group: pd.DataFrame) -> str:
                out: list[str] = []
                seen: set[str] = set()
                for _, row in group.iterrows():
                    txt = str(row.get("comment", "") or "").strip()
                    if not txt:
                        continue
                    cid = str(row.get("campaign_id", "") or "").strip()
                    if cid.lower() == "all":
                        label = "all"
                    else:
                        label = str(campaign_title_map.get(cid) or "").strip()
                    item = f"{label}: {txt}" if label else txt
                    if item not in seen:
                        seen.add(item)
                        out.append(item)
                return "\n\n".join(out)

            day_comment_map = comments_period.groupby("day").apply(_merge_day_comments).to_dict()
        else:
            day_comment_map = {}
        df_daily_raw["comment"] = df_daily_raw["day"].astype(str).map(day_comment_map).fillna("")
    else:
        df_daily_raw["comment"] = ""

    df_daily_raw["bid_changes_cnt"] = (
        df_daily_raw["day"].astype(str).map(bid_changes_day_map).fillna(0).astype(int)
    )
    df_daily_raw["day_dt"] = pd.to_datetime(df_daily_raw["day"], errors="coerce")
    df_daily_raw = df_daily_raw.sort_values("day_dt", ascending=False).drop(columns=["day_dt"], errors="ignore")
    return df_daily_raw


def _campaign_weekly_aggregate(df_daily_raw: pd.DataFrame, target_drr_pct: float) -> pd.DataFrame:
    if df_daily_raw.empty:
        return pd.DataFrame()

    dfw = df_daily_raw.copy()
    dfw["day"] = pd.to_datetime(dfw["day"]).dt.date
    dfw["week_start"] = dfw["day"].apply(lambda day: day - timedelta(days=day.weekday()))
    dfw["day_str"] = dfw["day"].astype(str)
    if "orders" not in dfw.columns:
        dfw["orders"] = 0
    if "orders_money_ads" not in dfw.columns:
        if "organic_pct" in dfw.columns and "total_revenue" in dfw.columns:
            revenue = pd.to_numeric(dfw["total_revenue"], errors="coerce").fillna(0.0)
            organic = pd.to_numeric(dfw["organic_pct"], errors="coerce").fillna(0.0).clip(lower=0.0, upper=100.0)
            dfw["orders_money_ads"] = (revenue * (100.0 - organic) / 100.0).fillna(0.0)
        else:
            dfw["orders_money_ads"] = 0.0
    if "ebitda" not in dfw.columns:
        dfw["ebitda"] = 0.0

    agg = (
        dfw.groupby("week_start", as_index=False)
        .agg(
            days_in_period=("day_str", "nunique"),
            money_spent=("money_spent", "sum"),
            views=("views", "sum"),
            clicks=("clicks", "sum"),
            orders=("orders", "sum"),
            orders_money_ads=("orders_money_ads", "sum"),
            total_revenue=("total_revenue", "sum"),
            ordered_units=("ordered_units", "sum"),
            ebitda=("ebitda", "sum"),
        )
        .sort_values("week_start")
    )

    target_drr = float(target_drr_pct) / 100.0
    agg["click_price"] = agg.apply(lambda row: (row["money_spent"] / row["clicks"]) if row["clicks"] else 0.0, axis=1)
    agg["ctr"] = agg.apply(lambda row: (row["clicks"] / row["views"] * 100.0) if row["views"] else 0.0, axis=1)
    agg["cr"] = agg.apply(
        lambda row: (row["ordered_units"] / row["clicks"] * 100.0) if row["clicks"] else 0.0,
        axis=1,
    )
    agg["vor"] = agg.apply(
        lambda row: (row["ordered_units"] / row["views"] * 100.0) if row["views"] else 0.0,
        axis=1,
    )
    agg["cpm"] = agg.apply(lambda row: (row["money_spent"] / row["views"] * 1000.0) if row["views"] else 0.0, axis=1)
    agg["total_drr_pct"] = agg.apply(
        lambda row: (row["money_spent"] / row["total_revenue"] * 100.0) if row["total_revenue"] else 0.0,
        axis=1,
    )
    agg["rpc"] = agg.apply(lambda row: (row["total_revenue"] / row["clicks"]) if row["clicks"] else 0.0, axis=1)
    agg["target_cpc"] = agg["rpc"] * target_drr
    agg["vpo"] = agg.apply(
        lambda row: (row["views"] / row["ordered_units"]) if row["ordered_units"] else 0.0,
        axis=1,
    )
    agg["ipo"] = agg.apply(
        lambda row: (row["views"] / row["ordered_units"]) if row["ordered_units"] else 0.0,
        axis=1,
    )
    agg["organic_pct"] = agg.apply(
        lambda row: (100.0 - (row["orders_money_ads"] / row["total_revenue"] * 100.0))
        if row["total_revenue"]
        else 0.0,
        axis=1,
    ).clip(lower=0.0, upper=100.0)
    agg["ebitda_pct"] = agg.apply(
        lambda row: (row["ebitda"] / row["total_revenue"] * 100.0) if row["total_revenue"] else 0.0,
        axis=1,
    )
    agg["week"] = agg["week_start"].astype(str)
    agg["week_dt"] = pd.to_datetime(agg["week"], errors="coerce")
    agg = agg.sort_values("week_dt", ascending=False).drop(columns=["week_dt", "week_start"], errors="ignore")
    return agg


def get_main_overview(*, company: str | None, date_from: str, date_to: str, target_drr_pct: float = 20.0) -> dict:
    company_name, config = resolve_company_config(company)
    perf_client_id = (config.get("perf_client_id") or "").strip() or None
    perf_client_secret = (config.get("perf_client_secret") or "").strip() or None
    seller_client_id = (config.get("seller_client_id") or "").strip() or None
    seller_api_key = (config.get("seller_api_key") or "").strip() or None

    running_campaigns = get_running_campaigns(client_id=perf_client_id, client_secret=perf_client_secret)
    daily_df = _daily_rows_with_legacy_main_logic(
        company_name=company_name,
        running_campaigns=running_campaigns,
        date_from=date_from,
        date_to=date_to,
        seller_client_id=seller_client_id,
        seller_api_key=seller_api_key,
        perf_client_id=perf_client_id,
        perf_client_secret=perf_client_secret,
        target_drr_pct=target_drr_pct,
    )

    weekly_df = _campaign_weekly_aggregate(daily_df, target_drr_pct=target_drr_pct)

    weekly_comment_map: dict[str, str] = {}
    weekly_bid_changes_map: dict[str, int] = {}
    if not daily_df.empty:
        comments_df = load_campaign_comments_df()
        if comments_df is not None and not comments_df.empty:
            if "company" in comments_df.columns:
                comments_df = comments_df[comments_df["company"].astype(str) == str(company_name)].copy()
            comments_period = comments_df[
                (comments_df["day"].astype(str) >= str(date_from))
                & (comments_df["day"].astype(str) <= str(date_to))
            ].copy()
            if not comments_period.empty:
                comments_period["week"] = (
                    pd.to_datetime(comments_period["day"], errors="coerce")
                    .dt.to_period("W-SUN")
                    .dt.start_time
                    .dt.date
                    .astype(str)
                )

                def _merge_week_comments(group: pd.DataFrame) -> str:
                    out: list[str] = []
                    seen: set[str] = set()
                    for _, row in group.sort_values(["day", "ts"], ascending=[False, False]).iterrows():
                        txt = str(row.get("comment", "") or "").strip()
                        if not txt:
                            continue
                        day_str = str(row.get("day", "") or "").strip()
                        item = f"{day_str}: {txt}" if day_str else txt
                        if item in seen:
                            continue
                        seen.add(item)
                        out.append(item)
                    return "\n\n".join(out)

                weekly_comment_map = comments_period.groupby("week").apply(_merge_week_comments).to_dict()

        bid_log_df = load_bid_changes_df()
        if bid_log_df is not None and not bid_log_df.empty:
            campaign_ids_set = {str(campaign.get("id")) for campaign in running_campaigns if campaign.get("id") is not None}
            bid_log_df = bid_log_df.copy()
            bid_log_df["campaign_id"] = bid_log_df["campaign_id"].astype(str)
            bid_log_df = bid_log_df[bid_log_df["campaign_id"].isin(campaign_ids_set)]
            if not bid_log_df.empty:
                bid_log_df["date"] = pd.to_datetime(bid_log_df["date"], errors="coerce")
                bid_log_df = bid_log_df.dropna(subset=["date"])
                if not bid_log_df.empty:
                    bid_log_df["week"] = bid_log_df["date"].dt.date.apply(
                        lambda day: day - timedelta(days=day.weekday())
                    ).astype(str)
                    weekly_bid_changes_map = {
                        str(key): int(value)
                        for key, value in bid_log_df.groupby("week").size().to_dict().items()
                    }

    if not weekly_df.empty:
        weekly_df["comment"] = weekly_df["week"].astype(str).map(weekly_comment_map).fillna("")
        weekly_df["bid_changes_cnt"] = weekly_df["week"].astype(str).map(weekly_bid_changes_map).fillna(0).astype(int)
        if "days_in_period" in weekly_df.columns:
            days_den = pd.to_numeric(weekly_df["days_in_period"], errors="coerce").replace(0, pd.NA)
            for src_col, dst_col in (
                ("total_revenue", "total_revenue_per_day"),
                ("money_spent", "money_spent_per_day"),
                ("views", "views_per_day"),
                ("clicks", "clicks_per_day"),
                ("ordered_units", "ordered_units_per_day"),
            ):
                if src_col in weekly_df.columns:
                    src = pd.to_numeric(weekly_df[src_col], errors="coerce").fillna(0)
                    weekly_df[dst_col] = (src / days_den).fillna(0).round(0)

    daily_columns = [
        "day",
        "total_revenue",
        "total_drr_pct",
        "money_spent",
        "views",
        "clicks",
        "ordered_units",
        "ctr",
        "cr",
        "organic_pct",
        "bid_changes_cnt",
        "comment",
    ]
    weekly_columns = [
        "week",
        "total_revenue",
        "total_drr_pct",
        "ebitda",
        "ebitda_pct",
        "total_revenue_per_day",
        "money_spent_per_day",
        "views_per_day",
        "clicks_per_day",
        "ordered_units_per_day",
        "ctr",
        "cr",
        "organic_pct",
        "bid_changes_cnt",
        "comment",
    ]
    chart_rows = []
    if not daily_df.empty:
        chart_source = daily_df.copy()
        chart_source["day"] = chart_source["day"].astype(str)
        chart_source["day_dt"] = pd.to_datetime(chart_source["day"], errors="coerce")
        chart_source = chart_source.sort_values("day_dt")
        chart_rows = [
            {
                "day": str(row["day"]),
                "total_revenue": float(_to_float(row.get("total_revenue"))),
                "money_spent": float(_to_float(row.get("money_spent"))),
                "total_drr_pct": float(_to_float(row.get("total_drr_pct"))),
            }
            for _, row in chart_source.iterrows()
        ]

    return {
        "company": company_name,
        "date_from": date_from,
        "date_to": date_to,
        "target_drr_pct": float(target_drr_pct),
        "chart_rows": chart_rows,
        "daily_rows": daily_df[[column for column in daily_columns if column in daily_df.columns]].to_dict("records")
        if not daily_df.empty
        else [],
        "weekly_rows": weekly_df[[column for column in weekly_columns if column in weekly_df.columns]].to_dict("records")
        if not weekly_df.empty
        else [],
    }
