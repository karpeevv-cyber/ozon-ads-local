from datetime import date
import sys
from pathlib import Path
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent / "backend"))

from app.services.finance_summary import get_finance_summary


class FinanceSummaryTests(unittest.TestCase):
    def test_finance_summary_maps_pickup_point_storage_service(self):
        payload = {
            "total": {
                "opening_balance": {"value": 0},
                "closing_balance": {"value": 0},
                "accrued": {"value": -3252},
                "payments": [],
            },
            "cashflows": {
                "sales": {"amount": {"value": 0}, "fee": {"value": 0}},
                "services": [
                    {"name": "temporary_placement_agent", "amount": {"value": -3252}},
                ],
            },
        }

        with (
            patch("app.services.finance_summary.resolve_company_config", return_value=("aura", {"seller_client_id": "1", "seller_api_key": "k"})),
            patch("app.services.finance_summary.seller_finance_balance", return_value=payload),
        ):
            summary = get_finance_summary(company="aura", date_from="2026-06-21", date_to="2026-06-21")

        self.assertEqual(summary["rows"][0]["day"], date(2026, 6, 21).isoformat())
        self.assertEqual(summary["rows"][0]["pickup_point_storage"], -3252)
        self.assertEqual(summary["totals"]["pickup_point_storage"], -3252)

    def test_finance_summary_maps_defect_processing_service(self):
        payload = {
            "total": {
                "opening_balance": {"value": 0},
                "closing_balance": {"value": 0},
                "accrued": {"value": -540},
                "payments": [],
            },
            "cashflows": {
                "sales": {"amount": {"value": 0}, "fee": {"value": 0}},
                "services": [
                    {"name": "defect_processing", "amount": {"value": -540}},
                ],
            },
        }

        with (
            patch("app.services.finance_summary.resolve_company_config", return_value=("aura", {"seller_client_id": "1", "seller_api_key": "k"})),
            patch("app.services.finance_summary.seller_finance_balance", return_value=payload),
        ):
            summary = get_finance_summary(company="aura", date_from="2026-06-07", date_to="2026-06-07")

        self.assertEqual(summary["rows"][0]["day"], date(2026, 6, 7).isoformat())
        self.assertEqual(summary["rows"][0]["defects"], -540)
        self.assertEqual(summary["totals"]["defects"], -540)

    def test_finance_summary_maps_payment_commission_services(self):
        payload = self._payload_with_services(
            [
                {"name": "flexible_payment_schedule", "amount": {"value": -38.3}},
                {"name": "early_payment", "amount": {"value": -674.07}},
            ],
            accrued=-712.37,
        )

        summary = self._summary_for("2026-06-30", payload)

        self.assertEqual(summary["rows"][0]["payment_commission"], -712)
        self.assertEqual(summary["totals"]["payment_commission"], -712)

    def test_finance_summary_maps_mutual_offset_service(self):
        payload = self._payload_with_services(
            [{"name": "offset_of_claims_between_contracts", "amount": {"value": -317.12}}],
            accrued=-317.12,
        )

        summary = self._summary_for("2026-06-28", payload)

        self.assertEqual(summary["rows"][0]["mutual_offset"], -317)
        self.assertEqual(summary["totals"]["mutual_offset"], -317)

    def test_finance_summary_maps_decompensation_service(self):
        payload = self._payload_with_services(
            [{"name": "decompensation_and_return_to_warehouse", "amount": {"value": -427}}],
            accrued=-427,
        )

        summary = self._summary_for("2026-06-29", payload)

        self.assertEqual(summary["rows"][0]["decompensation"], -427)
        self.assertEqual(summary["totals"]["decompensation"], -427)

    def test_finance_summary_maps_disposal_service(self):
        payload = self._payload_with_services(
            [{"name": "product_disposal", "amount": {"value": -225}}],
            accrued=-225,
        )

        summary = self._summary_for("2026-06-08", payload)

        self.assertEqual(summary["rows"][0]["disposal"], -225)
        self.assertEqual(summary["totals"]["disposal"], -225)

    def test_finance_summary_adds_shelf_life_processing_to_errors(self):
        payload = self._payload_with_services(
            [
                {"name": "booking_space_and_staff_for_partial_shipment", "amount": {"value": -15}},
                {"name": "goods_shelf_life_processing", "amount": {"value": -130}},
            ],
            accrued=-145,
        )

        summary = self._summary_for("2026-06-04", payload)

        self.assertEqual(summary["rows"][0]["errors"], -145)
        self.assertEqual(summary["totals"]["errors"], -145)

    def test_finance_summary_calculates_avoidable_costs(self):
        payload = self._payload_with_services(
            [
                {"name": "early_payment", "amount": {"value": -100}},
                {"name": "temporary_placement_agent", "amount": {"value": -200}},
                {"name": "booking_space_and_staff_for_partial_shipment", "amount": {"value": -300}},
                {"name": "defect_processing", "amount": {"value": -400}},
                {"name": "offset_of_claims_between_contracts", "amount": {"value": -500}},
                {"name": "decompensation_and_return_to_warehouse", "amount": {"value": -600}},
                {"name": "product_disposal", "amount": {"value": -700}},
                {"name": "ozon_warehouse_pickup", "amount": {"value": -800}},
                {"name": "product_placement_in_ozon_warehouses", "amount": {"value": -900}},
            ],
            accrued=-4500,
        )

        summary = self._summary_for("2026-07-06", payload)

        self.assertEqual(summary["rows"][0]["avoidable"], -4500)
        self.assertEqual(summary["totals"]["avoidable"], -4500)

    def test_finance_summary_uses_seller_analytics_revenue(self):
        payload = self._payload_with_services([], accrued=0)
        payload["cashflows"]["sales"]["amount"]["value"] = 1270

        with (
            patch("app.services.finance_summary.resolve_company_config", return_value=("aura", {"seller_client_id": "1", "seller_api_key": "k"})),
            patch("app.services.finance_summary.seller_finance_balance", return_value=payload),
            patch(
                "app.services.finance_summary.seller_analytics_sku_day",
                return_value=({}, {"2026-07-12": (4950.0, 7)}, {}),
            ),
        ):
            summary = get_finance_summary(company="aura", date_from="2026-07-12", date_to="2026-07-12")

        self.assertEqual(summary["rows"][0]["sales"], 4950)
        self.assertEqual(summary["rows"][0]["revenue"], 4950)
        self.assertEqual(summary["rows"][0]["finance_sales"], 1270)
        self.assertEqual(summary["totals"]["revenue"], 4950)

    def _summary_for(self, day: str, payload: dict):
        with (
            patch("app.services.finance_summary.resolve_company_config", return_value=("aura", {"seller_client_id": "1", "seller_api_key": "k"})),
            patch("app.services.finance_summary.seller_finance_balance", return_value=payload),
            patch("app.services.finance_summary.seller_analytics_sku_day", return_value=({}, {}, {})),
        ):
            return get_finance_summary(company="aura", date_from=day, date_to=day)

    def _payload_with_services(self, services: list[dict], *, accrued: float):
        return {
            "total": {
                "opening_balance": {"value": 0},
                "closing_balance": {"value": 0},
                "accrued": {"value": accrued},
                "payments": [],
            },
            "cashflows": {
                "sales": {"amount": {"value": 0}, "fee": {"value": 0}},
                "services": services,
            },
        }
