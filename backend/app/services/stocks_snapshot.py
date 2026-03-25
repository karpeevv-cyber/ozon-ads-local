from __future__ import annotations

import pandas as pd

from app.services.company_config import resolve_company_config
from app.services.legacy_compat import build_stocks_rows


def get_stocks_snapshot(*, company: str | None = None) -> dict:
    company_name, config = resolve_company_config(company)
    seller_client_id = (config.get("seller_client_id") or "").strip()
    seller_api_key = (config.get("seller_api_key") or "").strip()

    if not seller_client_id or not seller_api_key:
        return {
            "company": company_name,
            "seller_client_id": seller_client_id,
            "rows": [],
            "sku_count": 0,
        }

    rows, sku_count = build_stocks_rows(
        seller_client_id=seller_client_id,
        seller_api_key=seller_api_key,
    )

    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.sort_values(["article", "cluster"], ascending=[True, True]).reset_index(drop=True)

    return {
        "company": company_name,
        "seller_client_id": seller_client_id,
        "rows": df.to_dict("records") if not df.empty else [],
        "sku_count": sku_count,
    }
