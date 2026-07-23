"use client";

import { useState } from "react";

import { RunningCalendar } from "@/features/additional/components/RunningCalendar";
import { RunningGoals } from "@/features/additional/components/RunningGoals";


export function AdditionalWorkspace() {
  const [goalRefreshKey, setGoalRefreshKey] = useState(0);

  return (
    <section className="running-workspace">
      <RunningGoals refreshKey={goalRefreshKey} />
      <RunningCalendar onWorkoutsChanged={() => setGoalRefreshKey((value) => value + 1)} />
    </section>
  );
}
