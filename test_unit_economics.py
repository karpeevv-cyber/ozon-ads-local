import sys
from pathlib import Path
import unittest

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent / "backend"))

from app.services.unit_economics import _apply_unit_econ_costs


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


if __name__ == "__main__":
    unittest.main()
