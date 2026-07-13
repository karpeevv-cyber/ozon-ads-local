from __future__ import annotations

import math
from datetime import date, timedelta

from app.services.company_config import resolve_company_config
from app.services.integrations.ozon_seller import seller_analytics_sku_day, seller_finance_balance


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
    try:
        _by_sku, revenue_by_day, _by_day_sku = seller_analytics_sku_day(
            date_from,
            date_to,
            limit=1000,
            client_id=seller_client_id,
            api_key=seller_api_key,
        )
    except Exception:
        revenue_by_day = {}
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
        revenue, _ordered_units = revenue_by_day.get(day_str, (0.0, 0))
        fee = cashflows.get("sales", {}).get("fee", {}).get("value", 0)

        services = cashflows.get("services", []) or []
        logistics = 0.0
        storage = 0.0
        marketing = 0.0
        promotion_with_cpo = 0.0
        acquiring = 0.0
        payment_commission = 0.0
        returns_processing = 0.0
        reverse_logistics = 0.0
        cross_docking = 0.0
        export = 0.0
        pickup_point_storage = 0.0
        acceptance = 0.0
        errors = 0.0
        defects = 0.0
        mutual_offset = 0.0
        decompensation = 0.0
        disposal = 0.0
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
            if name in {"ozon_warehouse_pickup", "ozon_warehouse_pickup_assortment"}:
                export += value
            if name == "temporary_placement_agent":
                pickup_point_storage += value
            if name == "goods_processing_in_shipment":
                acceptance += value
            if name in {
                "booking_space_and_staff_for_partial_shipment",
                "processing_of_identified_surpluses_in_shipment",
                "goods_shelf_life_processing",
            }:
                errors += value
            if name == "defect_processing":
                defects += value
            if name == "offset_of_claims_between_contracts":
                mutual_offset += value
            if name == "decompensation_and_return_to_warehouse":
                decompensation += value
            if name == "product_disposal":
                disposal += value
            if name == "product_placement_in_ozon_warehouses":
                storage += value
            if name == "pay_per_click":
                marketing += value
            if name == "promotion_with_cost_per_order":
                promotion_with_cpo += value
            if name == "acquiring":
                acquiring += value
            if name in {"flexible_payment_schedule", "early_payment"}:
                payment_commission += value
            if name == "partner_returns_cancellations_processing":
                returns_processing += value
            if name == "seller_bonuses":
                seller_bonuses += value
            if name == "points_for_reviews":
                points_for_reviews += value

        sales_val = float(revenue or 0)
        pct_logistics = (logistics / sales_val * 100.0) if sales_val else 0.0
        check_value = (
            float(sales or 0)
            + float(fee or 0)
            + acquiring
            + payment_commission
            + logistics
            + reverse_logistics
            + returns_processing
            + cross_docking
            + export
            + pickup_point_storage
            + acceptance
            + errors
            + defects
            + mutual_offset
            + decompensation
            + disposal
            + storage
            + marketing
            + promotion_with_cpo
            + points_for_reviews
            + seller_bonuses
            - float(accrued or 0)
        )
        avoidable = (
            payment_commission
            + export
            + pickup_point_storage
            + errors
            + defects
            + mutual_offset
            + decompensation
            + disposal
            + storage
        )

        rows.append(
            {
                "day": day_str,
                "opening_balance": _ceil_int(opening_balance),
                "closing_balance": _ceil_int(closing_balance),
                "change": _ceil_int(accrued),
                "avoidable": _ceil_int(avoidable),
                "sales": _ceil_int(revenue),
                "revenue": _ceil_int(revenue),
                "finance_sales": _ceil_int(sales),
                "fee": _ceil_int(fee),
                "acquiring": _ceil_int(acquiring),
                "payments": _ceil_int(payments),
                "payment_commission": _ceil_int(payment_commission),
                "logistics": _ceil_int(logistics),
                "reverse_logistics": _ceil_int(reverse_logistics),
                "returns": _ceil_int(returns_processing),
                "cross_docking": _ceil_int(cross_docking),
                "export": _ceil_int(export),
                "pickup_point_storage": _ceil_int(pickup_point_storage),
                "acceptance": _ceil_int(acceptance),
                "errors": _ceil_int(errors),
                "defects": _ceil_int(defects),
                "mutual_offset": _ceil_int(mutual_offset),
                "decompensation": _ceil_int(decompensation),
                "disposal": _ceil_int(disposal),
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
        totals["logistics_pct"] = round(
            sum(float(row.get("logistics_pct") or 0) for row in rows) / len(rows),
            1,
        ) if rows else 0.0

    return {
        "company": company_name,
        "date_from": date_from,
        "date_to": date_to,
        "rows": rows,
        "totals": totals,
    }
