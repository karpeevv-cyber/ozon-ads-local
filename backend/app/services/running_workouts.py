from __future__ import annotations

import re
from datetime import date

from sqlalchemy.orm import Session

from app.models.running_workout import RunningWorkout
from app.repositories.running_workouts import delete_for_user_date, list_for_user, save_for_user_date
from app.schemas.running import RunningWorkoutResponse, RunningWorkoutUpsertRequest


PACE_PATTERN = re.compile(r"^(\d{1,2}):([0-5]\d)$")
DURATION_PATTERN = re.compile(r"^(?:(\d+):)?(\d{1,2}):([0-5]\d)$")


def _pace_to_seconds(value: str) -> int:
    match = PACE_PATTERN.fullmatch(value.strip())
    if not match:
        raise ValueError("Pace must use mm:ss format")
    seconds = int(match.group(1)) * 60 + int(match.group(2))
    if seconds <= 0:
        raise ValueError("Pace must be greater than zero")
    return seconds


def _duration_to_seconds(value: str) -> int:
    match = DURATION_PATTERN.fullmatch(value.strip())
    if not match:
        raise ValueError("Duration must use mm:ss or h:mm:ss format")
    hours = int(match.group(1) or 0)
    minutes = int(match.group(2))
    seconds = int(match.group(3))
    if match.group(1) is not None and minutes >= 60:
        raise ValueError("Minutes must be below 60 in h:mm:ss format")
    total = hours * 3600 + minutes * 60 + seconds
    if total <= 0:
        raise ValueError("Duration must be greater than zero")
    return total


def _format_pace(total_seconds: int) -> str:
    return f"{total_seconds // 60}:{total_seconds % 60:02d}"


def _format_duration(total_seconds: int) -> str:
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{seconds:02d}"
    return f"{minutes}:{seconds:02d}"


def serialize(workout: RunningWorkout) -> RunningWorkoutResponse:
    return RunningWorkoutResponse(
        date=workout.workout_date,
        distance=workout.distance_km,
        pace=_format_pace(workout.pace_seconds_per_km),
        duration=_format_duration(workout.duration_seconds),
        heart_rate=workout.average_heart_rate,
        type=workout.workout_type,
        calculated_from=workout.calculated_from,
    )


def list_workouts(db: Session, user_id: int) -> list[RunningWorkoutResponse]:
    return [serialize(workout) for workout in list_for_user(db, user_id)]


def upsert_workout(
    db: Session,
    *,
    user_id: int,
    workout_date: date,
    payload: RunningWorkoutUpsertRequest,
) -> RunningWorkoutResponse:
    workout = save_for_user_date(
        db,
        user_id=user_id,
        workout_date=workout_date,
        distance_km=round(payload.distance, 2),
        pace_seconds_per_km=_pace_to_seconds(payload.pace),
        duration_seconds=_duration_to_seconds(payload.duration),
        average_heart_rate=payload.heart_rate,
        workout_type=payload.type,
        calculated_from=payload.calculated_from,
    )
    return serialize(workout)


def delete_workout(db: Session, *, user_id: int, workout_date: date) -> bool:
    return delete_for_user_date(db, user_id, workout_date)
