from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Date, DateTime, Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class RunningWorkout(Base):
    __tablename__ = "running_workouts"
    __table_args__ = (
        UniqueConstraint("user_id", "workout_date", name="uq_running_workout_user_date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    workout_date: Mapped[date] = mapped_column(Date, index=True, nullable=False)
    distance_km: Mapped[float] = mapped_column(Float, nullable=False)
    pace_seconds_per_km: Mapped[int] = mapped_column(Integer, nullable=False)
    duration_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    average_heart_rate: Mapped[int] = mapped_column(Integer, nullable=False)
    workout_type: Mapped[str] = mapped_column(String(32), nullable=False)
    calculated_from: Mapped[str | None] = mapped_column(String(16), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )
