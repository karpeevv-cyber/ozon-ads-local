from __future__ import annotations

import argparse
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = REPO_ROOT / "backend"
sys.path.insert(0, str(BACKEND_ROOT))

from app.core.security import get_password_hash
from app.db.bootstrap import create_all
from app.db.session import SessionLocal
from app.models.user import User


def main() -> int:
    parser = argparse.ArgumentParser(description="Create or update an admin user")
    parser.add_argument("--email", required=True)
    parser.add_argument("--password", required=True)
    parser.add_argument("--full-name", dest="full_name", default="Admin")
    args = parser.parse_args()

    create_all()
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == args.email).first()
        hashed = get_password_hash(args.password)
        if user is None:
            user = User(
                email=args.email,
                password_hash=hashed,
                full_name=args.full_name,
                is_active=True,
                is_admin=True,
            )
            db.add(user)
        else:
            user.password_hash = hashed
            user.full_name = args.full_name
            user.is_active = True
            user.is_admin = True
        db.commit()
        print(f"admin_ready email={args.email}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
