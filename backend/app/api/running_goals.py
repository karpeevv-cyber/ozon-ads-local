from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.running_goal import RunningGoalPayload, RunningGoalResponse
from app.services.running_goals import create_goal, delete_goal, list_goals, update_goal


router = APIRouter(prefix="/running/goals", tags=["running"])


@router.get("", response_model=list[RunningGoalResponse])
def goals(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[RunningGoalResponse]:
    return list_goals(db, current_user.id)


@router.post("", response_model=RunningGoalResponse, status_code=status.HTTP_201_CREATED)
def add_goal(
    payload: RunningGoalPayload,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> RunningGoalResponse:
    return create_goal(db, user_id=current_user.id, payload=payload)


@router.put("/{goal_id}", response_model=RunningGoalResponse)
def replace_goal(
    goal_id: int,
    payload: RunningGoalPayload,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> RunningGoalResponse:
    goal = update_goal(db, user_id=current_user.id, goal_id=goal_id, payload=payload)
    if goal is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Goal not found")
    return goal


@router.delete("/{goal_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_goal(
    goal_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    if not delete_goal(db, user_id=current_user.id, goal_id=goal_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Goal not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
