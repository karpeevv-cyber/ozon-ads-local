from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.running_goal import RunningGoal
from app.repositories.running_goals import (
    create_for_user,
    delete_for_user,
    find_for_user,
    list_with_progress_for_user,
    progress_for_goal,
    update_for_user,
)
from app.schemas.running_goal import RunningGoalPayload, RunningGoalResponse


def _serialize(goal: RunningGoal, current_value: float) -> RunningGoalResponse:
    rounded_current = round(current_value, 2)
    progress_percent = round((rounded_current / goal.target_value) * 100, 1)
    return RunningGoalResponse(
        id=goal.id,
        title=goal.title,
        metric_type=goal.metric_type,
        target_value=goal.target_value,
        start_date=goal.start_date,
        current_value=rounded_current,
        progress_percent=progress_percent,
        completed=rounded_current >= goal.target_value,
    )


def list_goals(db: Session, user_id: int) -> list[RunningGoalResponse]:
    return [_serialize(goal, current_value) for goal, current_value in list_with_progress_for_user(db, user_id)]


def create_goal(db: Session, *, user_id: int, payload: RunningGoalPayload) -> RunningGoalResponse:
    goal = create_for_user(
        db,
        user_id=user_id,
        title=payload.title,
        metric_type=payload.metric_type,
        target_value=round(payload.target_value, 2),
        start_date=payload.start_date,
    )
    return _serialize(goal, progress_for_goal(db, goal))


def update_goal(
    db: Session,
    *,
    user_id: int,
    goal_id: int,
    payload: RunningGoalPayload,
) -> RunningGoalResponse | None:
    goal = find_for_user(db, user_id, goal_id)
    if goal is None:
        return None
    goal = update_for_user(
        db,
        goal,
        title=payload.title,
        metric_type=payload.metric_type,
        target_value=round(payload.target_value, 2),
        start_date=payload.start_date,
    )
    return _serialize(goal, progress_for_goal(db, goal))


def delete_goal(db: Session, *, user_id: int, goal_id: int) -> bool:
    goal = find_for_user(db, user_id, goal_id)
    if goal is None:
        return False
    delete_for_user(db, goal)
    return True
