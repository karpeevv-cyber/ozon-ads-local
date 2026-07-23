from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, field_validator


GoalMetricType = Literal["distance"]


class RunningGoalPayload(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    metric_type: GoalMetricType
    target_value: float = Field(gt=0, le=1_000_000)
    start_date: date

    @field_validator("title")
    @classmethod
    def normalize_title(cls, value: str) -> str:
        title = value.strip()
        if not title:
            raise ValueError("Goal title cannot be empty")
        return title


class RunningGoalResponse(RunningGoalPayload):
    id: int
    current_value: float
    progress_percent: float
    completed: bool
