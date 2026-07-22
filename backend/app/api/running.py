from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.running import RunningWorkoutResponse, RunningWorkoutUpsertRequest
from app.services.running_workouts import delete_workout, list_workouts, upsert_workout


router = APIRouter(prefix="/running/workouts", tags=["running"])


@router.get("", response_model=list[RunningWorkoutResponse])
def workouts(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[RunningWorkoutResponse]:
    return list_workouts(db, current_user.id)


@router.put("/{workout_date}", response_model=RunningWorkoutResponse)
def save_workout(
    workout_date: date,
    payload: RunningWorkoutUpsertRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> RunningWorkoutResponse:
    try:
        return upsert_workout(db, user_id=current_user.id, workout_date=workout_date, payload=payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc


@router.delete("/{workout_date}", status_code=status.HTTP_204_NO_CONTENT)
def remove_workout(
    workout_date: date,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    if not delete_workout(db, user_id=current_user.id, workout_date=workout_date):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workout not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
