from __future__ import annotations

import argparse
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd

from app.db.session import SessionLocal
from app.services.auto_bid_settings import save_campaign_bid_limit
from app.services.auto_bids import _iter_company_configs, build_company_bid_decisions
from app.services.bid_log import load_bid_changes_df


def _historical_bid_rub(
    changes: pd.DataFrame,
    *,
    campaign_id: str,
    sku: str,
    target_day: str,
    current_bid_rub: float,
) -> float:
    matching = changes[
        (changes["campaign_id"].astype(str) == campaign_id)
        & (changes["sku"].astype(str) == sku)
        & (changes["date"].astype(str) > target_day)
    ].sort_values(["ts_iso", "date"], kind="stable")
    if matching.empty:
        return current_bid_rub
    old_bid_micro = matching.iloc[0].get("old_bid_micro")
    if pd.isna(old_bid_micro) or float(old_bid_micro) <= 0:
        return current_bid_rub
    return float(old_bid_micro) / 1_000_000


def main() -> None:
    parser = argparse.ArgumentParser(description="Initialize per-campaign auto-bid limits from historical bids")
    parser.add_argument("--target-day", help="Historical state date in YYYY-MM-DD format")
    args = parser.parse_args()

    timezone = ZoneInfo("Europe/Moscow")
    target_day = args.target_day or (datetime.now(timezone).date() - timedelta(days=2)).isoformat()
    report_day = (datetime.now(timezone).date() - timedelta(days=1)).isoformat()
    changes = load_bid_changes_df()
    saved = 0

    with SessionLocal() as db:
        for config in _iter_company_configs():
            decisions = build_company_bid_decisions(config=config, day=report_day)
            for decision in decisions:
                if not decision.campaign_id or not decision.sku or decision.old_bid_rub is None:
                    continue
                max_bid_rub = _historical_bid_rub(
                    changes,
                    campaign_id=decision.campaign_id,
                    sku=decision.sku,
                    target_day=target_day,
                    current_bid_rub=decision.old_bid_rub,
                )
                save_campaign_bid_limit(
                    company_name=config.name,
                    campaign_id=decision.campaign_id,
                    sku=decision.sku,
                    max_bid_rub=max_bid_rub,
                    db=db,
                    commit=False,
                )
                saved += 1
                print(f"{config.name} {decision.article}: {max_bid_rub:g} RUB")
        db.commit()

    print(f"Saved {saved} limits for historical state at end of {target_day}")


if __name__ == "__main__":
    main()
