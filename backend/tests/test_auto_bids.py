from __future__ import annotations

import unittest

from app.services.auto_bids import _decide_bid


def _row(*, spend: float, revenue: float, units: int, bid: float = 20.0) -> dict:
    return {
        "campaign_id": "123",
        "sku": "456",
        "article": "Test_SKU",
        "money_spent": spend,
        "total_revenue": revenue,
        "ordered_units": units,
        "bid": bid,
    }


class AutoBidDecisionTests(unittest.TestCase):
    def test_low_spend_increases_bid_by_five_percent(self) -> None:
        decision = _decide_bid(
            company="test",
            day="2026-10-21",
            row=_row(spend=49, revenue=0, units=0),
        )

        self.assertEqual(decision.action, "increase")
        self.assertEqual(decision.new_bid_rub, 21.0)

    def test_high_spend_without_orders_decreases_bid_by_five_percent(self) -> None:
        decision = _decide_bid(
            company="test",
            day="2026-10-21",
            row=_row(spend=151, revenue=0, units=0),
        )

        self.assertEqual(decision.action, "decrease")
        self.assertEqual(decision.new_bid_rub, 19.0)

    def test_high_drr_decreases_bid_by_five_percent(self) -> None:
        decision = _decide_bid(
            company="test",
            day="2026-10-21",
            row=_row(spend=151, revenue=500, units=1),
        )

        self.assertEqual(decision.action, "decrease")
        self.assertEqual(decision.new_bid_rub, 19.0)


if __name__ == "__main__":
    unittest.main()
