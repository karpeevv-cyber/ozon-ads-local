from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field


WorkoutType = Literal["base", "intervals", "tempo", "long"]
CalculatedFrom = Literal["pace", "duration"]


class RunningWorkoutUpsertRequest(BaseModel):
    distance: float = Field(gt=0, le=1000)
    pace: str = Field(min_length=4, max_length=5)
    duration: str = Field(min_length=4, max_length=8)
    heart_rate: int = Field(ge=30, le=240)
    type: WorkoutType
    calculated_from: CalculatedFrom | None = None


class RunningWorkoutResponse(RunningWorkoutUpsertRequest):
    date: date
