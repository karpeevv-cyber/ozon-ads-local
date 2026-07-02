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
