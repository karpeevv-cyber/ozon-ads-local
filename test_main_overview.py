import json
import sys
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import MagicMock, patch

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent / "backend"))

from app.services.main_overview import get_main_overview_cached


class MainOverviewCacheTests(TestCase):
    def test_falls_back_to_latest_cache_when_ozon_performance_is_unavailable(self):
        response = requests.Response()
        response.status_code = 403
        error = requests.HTTPError("forbidden", response=response)
        cached_payload = {
            "company": "aura",
            "date_from": "2026-07-27",
            "date_to": "2026-08-29",
            "target_drr_pct": 20.0,
            "chart_rows": [],
            "daily_rows": [],
            "weekly_rows": [],
        }
        cached_row = SimpleNamespace(
            payload_json=json.dumps(cached_payload),
            updated_at=datetime(2026, 8, 28, 21, 11, 14),
        )

        exact_query = MagicMock()
        exact_query.filter.return_value = exact_query
        exact_query.first.return_value = None
        fallback_query = MagicMock()
        fallback_query.filter.return_value = fallback_query
        fallback_query.order_by.return_value = fallback_query
        fallback_query.first.return_value = cached_row
        db = MagicMock()
        db.query.side_effect = [exact_query, fallback_query]

        with (
            patch("app.services.main_overview.resolve_company_config", return_value=("aura", {})),
            patch("app.services.main_overview.create_all"),
            patch("app.services.main_overview.get_main_overview", side_effect=error),
        ):
            payload = get_main_overview_cached(
                company="aura",
                date_from="2026-08-03",
                date_to="2026-09-02",
                target_drr_pct=20.0,
                db=db,
            )

        self.assertTrue(payload["cache_hit"])
        self.assertEqual(payload["date_to"], "2026-08-29")
        self.assertIn("2026-07-27–2026-08-29", payload["warning"])
        db.commit.assert_not_called()
