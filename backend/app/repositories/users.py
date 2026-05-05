from __future__ import annotations

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.user import User


def get_user_by_email(db: Session, email: str) -> User | None:
    return db.query(User).filter(func.lower(User.email) == email.strip().lower()).first()


def create_user(db: Session, *, email: str, password_hash: str, full_name: str = "") -> User:
    user = User(
        email=email.strip().lower(),
        password_hash=password_hash,
        full_name=full_name.strip(),
        is_active=True,
        is_admin=False,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user
