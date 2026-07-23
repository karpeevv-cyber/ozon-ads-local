from __future__ import annotations

from datetime import date

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from app.models.running_goal import RunningGoal
from app.models.running_workout import RunningWorkout


def list_with_progress_for_user(db: Session, user_id: int) -> list[tuple[RunningGoal, float]]:
    progress = func.coalesce(func.sum(RunningWorkout.distance_km), 0.0)
    statement = (
        select(RunningGoal, progress)
        .outerjoin(
            RunningWorkout,
            and_(
                RunningWorkout.user_id == RunningGoal.user_id,
                RunningWorkout.workout_date >= RunningGoal.start_date,
            ),
        )
        .where(RunningGoal.user_id == user_id)
        .group_by(RunningGoal.id)
        .order_by(RunningGoal.created_at.desc(), RunningGoal.id.desc())
    )
    return [(goal, float(current_value)) for goal, current_value in db.execute(statement).all()]


def find_for_user(db: Session, user_id: int, goal_id: int) -> RunningGoal | None:
    return db.scalar(select(RunningGoal).where(RunningGoal.id == goal_id, RunningGoal.user_id == user_id))


def progress_for_goal(db: Session, goal: RunningGoal) -> float:
    statement = select(func.coalesce(func.sum(RunningWorkout.distance_km), 0.0)).where(
        RunningWorkout.user_id == goal.user_id,
        RunningWorkout.workout_date >= goal.start_date,
    )
    return float(db.scalar(statement) or 0.0)


def create_for_user(
    db: Session,
    *,
    user_id: int,
    title: str,
    metric_type: str,
    target_value: float,
    start_date: date,
) -> RunningGoal:
    goal = RunningGoal(
        user_id=user_id,
        title=title,
        metric_type=metric_type,
        target_value=target_value,
        start_date=start_date,
    )
    db.add(goal)
    db.commit()
    db.refresh(goal)
    return goal


def update_for_user(
    db: Session,
    goal: RunningGoal,
    *,
    title: str,
    metric_type: str,
    target_value: float,
    start_date: date,
) -> RunningGoal:
    goal.title = title
    goal.metric_type = metric_type
    goal.target_value = target_value
    goal.start_date = start_date
    db.commit()
    db.refresh(goal)
    return goal


def delete_for_user(db: Session, goal: RunningGoal) -> None:
    db.delete(goal)
    db.commit()
