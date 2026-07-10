from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
BACKEND_ROOT = ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


def _load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if not text or text.startswith("#") or "=" not in text:
            continue
        key, value = text.split("=", 1)
        key = key.strip()
        value = value.strip().strip("\"'")
        if key and key not in os.environ:
            os.environ[key] = value


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Ozon Ads auto-bids for yesterday.")
    parser.add_argument("--dry-run", action="store_true", help="Calculate and send Telegram report without applying bids.")
    parser.add_argument(
        "--no-telegram",
        action="store_true",
        help="Do not send Telegram report.",
    )
    args = parser.parse_args()

    _load_env_file(ROOT / ".env")

    dry_run_env = os.getenv("DRY_RUN", "").strip().lower() in {"1", "true", "yes", "on"}
    dry_run = bool(args.dry_run or dry_run_env)

    from app.services.auto_bids import run_auto_bids_for_yesterday

    decisions = run_auto_bids_for_yesterday(dry_run=dry_run, send_telegram=not args.no_telegram)
    changed = sum(1 for item in decisions if item.new_bid_rub is not None and not item.manual_review)
    manual = sum(1 for item in decisions if item.manual_review)
    print(f"auto bids finished: decisions={len(decisions)} changed={changed} manual={manual} dry_run={dry_run}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
