from __future__ import annotations

import math
from datetime import date, timedelta

from app.services.company_config import resolve_company_config
from app.services.integrations.ozon_seller import seller_finance_balance


def _daterange(d_from: date, d_to: date):
    current = d_from
    while current <= d_to:
        yield current
        current += timedelta(days=1)


def _ceil_int(value) -> int:
    try:
        return int(math.ceil(float(value)))
    except Exception:
        return 0


def get_finance_summary(*, company: str | None, date_from: str, date_to: str) -> dict:
    company_name, config = resolve_company_config(company)
    seller_client_id = (config.get("seller_client_id") or "").strip()
    seller_api_key = (config.get("seller_api_key") or "").strip()

    if not seller_client_id or not seller_api_key:
        return {
            "company": company_name,
            "date_from": date_from,
            "date_to": date_to,
            "rows": [],
            "totals": {},
        }

    start = date.fromisoformat(date_from)
    end = date.fromisoformat(date_to)
    rows = []
    for day in reversed(list(_daterange(start, end))):
        day_str = day.isoformat()
        data = seller_finance_balance(
            date_from=day_str,
            date_to=day_str,
            client_id=seller_client_id,
            api_key=seller_api_key,
        )
        total = data.get("total", {}) or {}
        cashflows = data.get("cashflows", {}) or {}

        opening_balance = total.get("opening_balance", {}).get("value", 0)
        closing_balance = total.get("closing_balance", {}).get("value", 0)
        accrued = total.get("accrued", {}).get("value", 0)
        payments = sum(float(p.get("value", 0) or 0) for p in (total.get("payments", []) or []))
        sales = cashflows.get("sales", {}).get("amount", {}).get("value", 0)
        fee = cashflows.get("sales", {}).get("fee", {}).get("value", 0)

        services = cashflows.get("services", []) or []
        logistics = 0.0
        storage = 0.0
        marketing = 0.0
        promotion_with_cpo = 0.0
        acquiring = 0.0
        returns_processing = 0.0
        reverse_logistics = 0.0
        cross_docking = 0.0
        acceptance = 0.0
        errors = 0.0
        seller_bonuses = 0.0
        points_for_reviews = 0.0
        for service in services:
            name = str(service.get("name", "") or "")
            value = float(service.get("amount", {}).get("value", 0) or 0)
            if name in {"logistics", "courier_client_reinvoice", "delivery_to_handover_place_by_ozon"}:
                logistics += value
            if name == "reverse_logistics":
                reverse_logistics += value
            if name == "cross_docking":
                cross_docking += value
            if name == "goods_processing_in_shipment":
                acceptance += value
            if name == "booking_space_and_staff_for_partial_shipment":
                errors += value
            if name == "product_placement_in_ozon_warehouses":
                storage += value
            if name == "pay_per_click":
                marketing += value
            if name == "promotion_with_cost_per_order":
                promotion_with_cpo += value
            if name == "acquiring":
                acquiring += value
            if name == "partner_returns_cancellations_processing":
                returns_processing += value
            if name == "seller_bonuses":
                seller_bonuses += value
            if name == "points_for_reviews":
                points_for_reviews += value

        sales_val = float(sales or 0)
        pct_logistics = (logistics / sales_val * 100.0) if sales_val else 0.0
        check_value = (
            float(sales or 0)
            + float(fee or 0)
            + acquiring
            + logistics
            + reverse_logistics
            + returns_processing
            + cross_docking
            + acceptance
            + errors
            + storage
            + marketing
            + promotion_with_cpo
            + points_for_reviews
            + seller_bonuses
            - float(accrued or 0)
        )

        rows.append(
            {
                "day": day_str,
                "opening_balance": _ceil_int(opening_balance),
                "closing_balance": _ceil_int(closing_balance),
                "change": _ceil_int(accrued),
                "sales": _ceil_int(sales),
                "fee": _ceil_int(fee),
                "acquiring": _ceil_int(acquiring),
                "payments": _ceil_int(payments),
                "logistics": _ceil_int(logistics),
                "reverse_logistics": _ceil_int(reverse_logistics),
                "returns": _ceil_int(returns_processing),
                "cross_docking": _ceil_int(cross_docking),
                "acceptance": _ceil_int(acceptance),
                "errors": _ceil_int(errors),
                "storage": _ceil_int(storage),
                "marketing": _ceil_int(marketing),
                "promotion_with_cpo": _ceil_int(promotion_with_cpo),
                "points_for_reviews": _ceil_int(points_for_reviews),
                "seller_bonuses": _ceil_int(seller_bonuses),
                "check": _ceil_int(check_value),
                "logistics_pct": round(pct_logistics, 1),
            }
        )

    totals: dict[str, float] = {}
    for row in rows:
        for key, value in row.items():
            if key == "day":
                continue
            totals[key] = float(totals.get(key, 0) or 0) + float(value or 0)
    if "logistics_pct" in totals:
        totals["logistics_pct"] = round(float(totals["logistics_pct"]), 1)

    return {
        "company": company_name,
        "date_from": date_from,
        "date_to": date_to,
        "rows": rows,
        "totals": totals,
    }
