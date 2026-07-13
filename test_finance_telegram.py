import os
import sys
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent / "backend"))

from app.services.finance_telegram import build_finance_telegram_message, resolve_company_chat_id


class FinanceTelegramTests(TestCase):
    def test_build_finance_telegram_message_uses_finance_page_columns(self):
        row = {
            "day": "2026-07-06",
            "opening_balance": 100,
            "closing_balance": 200,
            "change": 100,
            "avoidable": -2800,
            "sales": 1000,
            "revenue": 1000,
            "fee": -100,
            "acquiring": -20,
            "payments": -500,
            "payment_commission": -12,
            "logistics": -30,
            "reverse_logistics": -40,
            "returns": -5,
            "cross_docking": -6,
            "acceptance": -7,
            "export": -8,
            "pickup_point_storage": -9,
            "errors": -10,
            "defects": -11,
            "mutual_offset": -12,
            "decompensation": -13,
            "disposal": -14,
            "storage": -15,
            "marketing": -16,
            "promotion_with_cpo": -17,
            "points_for_reviews": -18,
            "seller_bonuses": -19,
            "check": 0,
            "logistics_pct": -3.0,
        }

        message = build_finance_telegram_message(company_name="aura", row=row)
        lines = message.splitlines()

        self.assertEqual(lines[:9], [
            "день: 2026-07-06",
            "продажи: 1000",
            "дрр: 3.3%",
            "",
            "на начало дня: 100",
            "на конец дня: 200",
            "изменение: 100",
            "возможно избежать: -2800",
            "",
        ])
        self.assertIn("день: 2026-07-06", message)
        self.assertIn("комиссия + эквайринг: -120", message)
        self.assertIn("обратная логистика + возвраты: -45", message)
        self.assertIn("кросс-докинг + приемка: -13", message)
        self.assertIn("комиссия за выплату: -12", message)
        self.assertIn("хранение товаров в ПВЗ: -9", message)
        self.assertIn("взаимозачет: -12", message)
        self.assertIn("декомпенсация: -13", message)
        self.assertIn("утилизация: -14", message)

    def test_resolve_company_chat_id_supports_company_specific_and_legacy_second_company(self):
        env = {
            "TG_CHAT_ID_AURA": "chat-aura",
            "TG_CHAT_ID": "chat-default",
            "TG_CHAT_ID_2": "chat-second",
            "COMPANY_NAME_2": "osome",
        }
        with patch.dict(os.environ, env, clear=True):
            self.assertEqual(resolve_company_chat_id("aura", 0, 2), "chat-aura")
            self.assertEqual(resolve_company_chat_id("osome", 1, 2), "chat-second")
