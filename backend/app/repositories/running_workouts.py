from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.running_workout import RunningWorkout


def list_for_user(db: Session, user_id: int) -> list[RunningWorkout]:
    statement = (
        select(RunningWorkout)
        .where(RunningWorkout.user_id == user_id)
        .order_by(RunningWorkout.workout_date.asc())
    )
    return list(db.scalars(statement).all())


def find_for_user_date(db: Session, user_id: int, workout_date: date) -> RunningWorkout | None:
    statement = select(RunningWorkout).where(
        RunningWorkout.user_id == user_id,
        RunningWorkout.workout_date == workout_date,
    )
    return db.scalar(statement)


def save_for_user_date(
    db: Session,
    *,
    user_id: int,
    workout_date: date,
    distance_km: float,
    pace_seconds_per_km: int,
    duration_seconds: int,
    average_heart_rate: int,
    workout_type: str,
    calculated_from: str | None,
) -> RunningWorkout:
    workout = find_for_user_date(db, user_id, workout_date)
    if workout is None:
        workout = RunningWorkout(user_id=user_id, workout_date=workout_date)
        db.add(workout)
    workout.distance_km = distance_km
    workout.pace_seconds_per_km = pace_seconds_per_km
    workout.duration_seconds = duration_seconds
    workout.average_heart_rate = average_heart_rate
    workout.workout_type = workout_type
    workout.calculated_from = calculated_from
    db.commit()
    db.refresh(workout)
    return workout


def delete_for_user_date(db: Session, user_id: int, workout_date: date) -> bool:
    workout = find_for_user_date(db, user_id, workout_date)
    if workout is None:
        return False
    db.delete(workout)
    db.commit()
    return True
