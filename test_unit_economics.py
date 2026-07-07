import sys
from pathlib import Path
import unittest
from unittest.mock import patch

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent / "backend"))

from app.services.unit_economics import _apply_unit_econ_costs, _load_finance_period_costs


class UnitEconomicsTests(unittest.TestCase):
    def test_ozon_percent_cost_uses_36_percent_above_300_rub(self):
        sales_df = pd.DataFrame(
            [
                {"sku": "1", "name": "cheap", "quantity": 1, "revenue": 300, "sale": 300},
                {"sku": "2", "name": "expensive", "quantity": 1, "revenue": 301, "sale": 301},
            ]
        )
        costs_df = pd.DataFrame(
            [
                {"sku": "1", "sheet_name": "cheap", "tea_cost": 0, "package_cost": 0, "label_cost": 0, "packing_cost": 0},
                {"sku": "2", "sheet_name": "expensive", "tea_cost": 0, "package_cost": 0, "label_cost": 0, "packing_cost": 0},
            ]
        )
        finance_costs = {
            "logistics": 0,
            "cross_docking": 0,
            "acceptance": 0,
            "marketing": 0,
            "promotion_with_cpo": 0,
            "acquiring": 0,
            "reverse_logistics": 0,
            "returns_processing": 0,
            "errors": 0,
            "storage": 0,
            "points_for_reviews": 0,
            "seller_bonuses": 0,
        }

        result = _apply_unit_econ_costs(sales_df, costs_df, finance_costs)

        by_sku = result.set_index("sku")
        self.assertAlmostEqual(by_sku.loc["1", "ozon_percent_cost"], 60.0)
        self.assertAlmostEqual(by_sku.loc["2", "ozon_percent_cost"], 108.36)

    def test_finance_costs_returns_avoidable_breakdown(self):
        payload = {
            "cashflows": {
                "services": [
                    {"name": "early_payment", "amount": {"value": -10}},
                    {"name": "ozon_warehouse_pickup", "amount": {"value": -20}},
                    {"name": "temporary_placement_agent", "amount": {"value": -30}},
                    {"name": "booking_space_and_staff_for_partial_shipment", "amount": {"value": -40}},
                    {"name": "defect_processing", "amount": {"value": -50}},
                    {"name": "offset_of_claims_between_contracts", "amount": {"value": -60}},
                    {"name": "decompensation_and_return_to_warehouse", "amount": {"value": -70}},
                    {"name": "product_disposal", "amount": {"value": -80}},
                    {"name": "product_placement_in_ozon_warehouses", "amount": {"value": -90}},
                ]
            }
        }

        with patch("app.services.unit_economics.seller_finance_balance", return_value=payload):
            costs = _load_finance_period_costs(
                "2026-07-06",
                "2026-07-06",
                seller_client_id="1",
                seller_api_key="k",
            )

        self.assertEqual(costs["avoidable"], -450)
        self.assertEqual(
            costs["avoidable_breakdown"],
            [
                {"label": "Комиссия за выплату", "amount": -10.0},
                {"label": "Вывоз со склада", "amount": -20.0},
                {"label": "Хранение в ПВЗ", "amount": -30.0},
                {"label": "Ошибки", "amount": -40.0},
                {"label": "Обработка брака", "amount": -50.0},
                {"label": "Взаимозачет", "amount": -60.0},
                {"label": "Декомпенсация", "amount": -70.0},
                {"label": "Утилизация", "amount": -80.0},
                {"label": "Хранение", "amount": -90.0},
            ],
        )


if __name__ == "__main__":
    unittest.main()
