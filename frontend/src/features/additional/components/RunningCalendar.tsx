"use client";

import { FormEvent, useEffect, useMemo, useRef, useState } from "react";

import { deleteRunningWorkout, getRunningWorkouts, saveRunningWorkout } from "@/shared/api/client";
import { RunningWorkoutPayload, RunningWorkoutRecord } from "@/shared/api/types";

type WorkoutType = "base" | "intervals" | "tempo" | "long";

type Workout = {
  date: string;
  distance: number;
  pace: string;
  duration?: string;
  calculatedFrom?: "pace" | "duration";
  heartRate: number;
  type: WorkoutType;
};

const LEGACY_STORAGE_KEY = "marketrix-running-workouts-v1";
const AUTH_TOKEN_KEY = "ozon_ads_token";

const WORKOUT_TYPES: Array<{ value: WorkoutType; label: string }> = [
  { value: "base", label: "Base" },
  { value: "intervals", label: "Intervals" },
  { value: "tempo", label: "Tempo" },
  { value: "long", label: "Long run" },
];

const WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

function dateKey(date: Date) {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function daysForCalendar(month: Date) {
  const first = new Date(month.getFullYear(), month.getMonth(), 1);
  const mondayOffset = (first.getDay() + 6) % 7;
  const gridStart = new Date(first.getFullYear(), first.getMonth(), 1 - mondayOffset);
  return Array.from({ length: 42 }, (_, index) => {
    const date = new Date(gridStart);
    date.setDate(gridStart.getDate() + index);
    return date;
  });
}

function paceToSeconds(pace: string) {
  const match = pace.trim().match(/^(\d{1,2}):([0-5]\d)$/);
  return match ? Number(match[1]) * 60 + Number(match[2]) : 0;
}

function durationToSeconds(duration: string) {
  const parts = duration.trim().split(":").map(Number);
  if (parts.length === 2 && parts.every(Number.isFinite) && parts[0] >= 0 && parts[1] >= 0 && parts[1] < 60) {
    return parts[0] * 60 + parts[1];
  }
  if (
    parts.length === 3 &&
    parts.every(Number.isFinite) &&
    parts[0] >= 0 &&
    parts[1] >= 0 &&
    parts[1] < 60 &&
    parts[2] >= 0 &&
    parts[2] < 60
  ) {
    return parts[0] * 3600 + parts[1] * 60 + parts[2];
  }
  return 0;
}

function secondsToPace(value: number) {
  const rounded = Math.round(value);
  const minutes = Math.floor(rounded / 60);
  const seconds = rounded % 60;
  return `${minutes}:${String(seconds).padStart(2, "0")}`;
}

function secondsToDuration(value: number) {
  const rounded = Math.round(value);
  const hours = Math.floor(rounded / 3600);
  const minutes = Math.floor((rounded % 3600) / 60);
  const seconds = rounded % 60;
  return hours > 0
    ? `${hours}:${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`
    : `${minutes}:${String(seconds).padStart(2, "0")}`;
}

function workoutDuration(workout: Workout) {
  return workout.duration || secondsToDuration(paceToSeconds(workout.pace) * workout.distance);
}

function fromApi(workout: RunningWorkoutRecord): Workout {
  return {
    date: workout.date,
    distance: workout.distance,
    pace: workout.pace,
    duration: workout.duration,
    calculatedFrom: workout.calculated_from ?? undefined,
    heartRate: workout.heart_rate,
    type: workout.type,
  };
}

function toApi(workout: Workout): RunningWorkoutPayload {
  return {
    distance: workout.distance,
    pace: workout.pace,
    duration: workoutDuration(workout),
    calculated_from: workout.calculatedFrom ?? null,
    heart_rate: workout.heartRate,
    type: workout.type,
  };
}

function workoutsByDate(rows: Workout[]) {
  return Object.fromEntries(rows.map((workout) => [workout.date, workout]));
}

export function RunningCalendar() {
  const [month, setMonth] = useState(() => {
    const today = new Date();
    return new Date(today.getFullYear(), today.getMonth(), 1);
  });
  const [workouts, setWorkouts] = useState<Record<string, Workout>>({});
  const [loaded, setLoaded] = useState(false);
  const [syncError, setSyncError] = useState("");
  const [saving, setSaving] = useState(false);
  const [selectedDate, setSelectedDate] = useState<string | null>(null);
  const [distance, setDistance] = useState("");
  const [pace, setPace] = useState("");
  const [duration, setDuration] = useState("");
  const [calculatedFrom, setCalculatedFrom] = useState<Workout["calculatedFrom"]>();
  const [heartRate, setHeartRate] = useState("");
  const [type, setType] = useState<WorkoutType>("base");
  const [error, setError] = useState("");
  const dialogRef = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    let cancelled = false;

    async function loadWorkouts() {
      const token = window.localStorage.getItem(AUTH_TOKEN_KEY);
      if (!token) {
        if (!cancelled) {
          setSyncError("Your session has expired. Sign in again to load training history.");
          setLoaded(true);
        }
        return;
      }

      let legacyWorkouts: Record<string, Workout> = {};
      try {
        const stored = window.localStorage.getItem(LEGACY_STORAGE_KEY);
        if (stored) legacyWorkouts = JSON.parse(stored) as Record<string, Workout>;
      } catch {
        // Ignore malformed legacy cache; server data remains authoritative.
      }

      try {
        const serverRows = (await getRunningWorkouts(token)).map(fromApi);
        const serverWorkouts = workoutsByDate(serverRows);
        const missingLegacyRows = Object.values(legacyWorkouts).filter((workout) => !serverWorkouts[workout.date]);
        try {
          const migratedRows = await Promise.all(
            missingLegacyRows.map(async (workout) => fromApi(await saveRunningWorkout(workout.date, toApi(workout), token))),
          );
          if (!cancelled) {
            setWorkouts({ ...serverWorkouts, ...workoutsByDate(migratedRows) });
            window.localStorage.removeItem(LEGACY_STORAGE_KEY);
          }
        } catch {
          if (!cancelled) {
            setWorkouts({ ...legacyWorkouts, ...serverWorkouts });
            setSyncError("Some browser-only workouts could not be moved to your account. They are still safe in this browser.");
          }
        }
      } catch (loadError) {
        if (!cancelled) {
          setWorkouts(legacyWorkouts);
          setSyncError(loadError instanceof Error ? loadError.message : "Could not load training history.");
        }
      } finally {
        if (!cancelled) setLoaded(true);
      }
    }

    void loadWorkouts();
    return () => {
      cancelled = true;
    };
  }, []);

  const days = useMemo(() => daysForCalendar(month), [month]);
  const monthWorkouts = useMemo(
    () =>
      Object.values(workouts).filter((workout) => {
        const date = new Date(`${workout.date}T12:00:00`);
        return date.getFullYear() === month.getFullYear() && date.getMonth() === month.getMonth();
      }),
    [month, workouts],
  );

  const totals = useMemo(() => {
    const totalDistance = monthWorkouts.reduce((sum, workout) => sum + workout.distance, 0);
    const paced = monthWorkouts.filter((workout) => paceToSeconds(workout.pace) > 0);
    const averagePace = paced.length
      ? secondsToPace(paced.reduce((sum, workout) => sum + paceToSeconds(workout.pace), 0) / paced.length)
      : "—";
    const averageHeartRate = monthWorkouts.length
      ? Math.round(monthWorkouts.reduce((sum, workout) => sum + workout.heartRate, 0) / monthWorkouts.length)
      : 0;
    return { totalDistance, averagePace, averageHeartRate };
  }, [monthWorkouts]);

  const calculationPreview = useMemo(() => {
    const numericDistance = Number(distance.replace(",", "."));
    const paceSeconds = paceToSeconds(pace);
    const durationSeconds = durationToSeconds(duration);
    if (!numericDistance || numericDistance <= 0) return "Distance is required.";
    if (paceSeconds > 0 && (!duration.trim() || calculatedFrom === "pace")) {
      return `Total time will be calculated: ${secondsToDuration(paceSeconds * numericDistance)}`;
    }
    if (durationSeconds > 0 && (!pace.trim() || calculatedFrom === "duration")) {
      return `Pace will be calculated: ${secondsToPace(durationSeconds / numericDistance)} /km`;
    }
    if (pace.trim() && duration.trim()) return "Pace and time will be saved exactly as entered.";
    return "Enter either pace or total time — the other value will be calculated.";
  }, [calculatedFrom, distance, duration, pace]);

  function openEditor(key: string) {
    const workout = workouts[key];
    setSelectedDate(key);
    setDistance(workout ? String(workout.distance) : "");
    setPace(workout?.pace ?? "");
    setDuration(workout?.duration ?? "");
    setCalculatedFrom(workout?.calculatedFrom);
    setHeartRate(workout ? String(workout.heartRate) : "");
    setType(workout?.type ?? "base");
    setError("");
    dialogRef.current?.showModal();
  }

  function closeEditor() {
    dialogRef.current?.close();
    setError("");
  }

  async function saveWorkout(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedDate) return;
    const numericDistance = Number(distance.replace(",", "."));
    const numericHeartRate = Number(heartRate);
    const enteredPace = pace.trim();
    const enteredDuration = duration.trim();
    const paceSeconds = paceToSeconds(enteredPace);
    const durationSeconds = durationToSeconds(enteredDuration);
    if (!numericDistance || numericDistance <= 0) {
      setError("Enter a distance greater than zero.");
      return;
    }
    if (!enteredPace && !enteredDuration) {
      setError("Enter either pace or total time. The other value will be calculated automatically.");
      return;
    }
    if (enteredPace && !paceSeconds) {
      setError("Use the pace format mm:ss, for example 5:25.");
      return;
    }
    if (enteredDuration && !durationSeconds) {
      setError("Use the total time format mm:ss or h:mm:ss, for example 48:30 or 1:05:20.");
      return;
    }
    if (!numericHeartRate || numericHeartRate < 30 || numericHeartRate > 240) {
      setError("Heart rate must be between 30 and 240 bpm.");
      return;
    }
    let savedPace = enteredPace;
    let savedDuration = enteredDuration;
    let nextCalculatedFrom: Workout["calculatedFrom"];
    if (enteredPace && (!enteredDuration || calculatedFrom === "pace")) {
      savedDuration = secondsToDuration(paceSeconds * numericDistance);
      nextCalculatedFrom = "pace";
    } else if (enteredDuration && (!enteredPace || calculatedFrom === "duration")) {
      savedPace = secondsToPace(durationSeconds / numericDistance);
      nextCalculatedFrom = "duration";
    }
    const workout: Workout = {
      date: selectedDate,
      distance: Math.round(numericDistance * 100) / 100,
      pace: savedPace,
      duration: savedDuration,
      calculatedFrom: nextCalculatedFrom,
      heartRate: Math.round(numericHeartRate),
      type,
    };
    const token = window.localStorage.getItem(AUTH_TOKEN_KEY);
    if (!token) {
      setError("Your session has expired. Sign in again before saving.");
      return;
    }
    setSaving(true);
    try {
      const saved = fromApi(await saveRunningWorkout(selectedDate, toApi(workout), token));
      setWorkouts((current) => ({ ...current, [selectedDate]: saved }));
      setSyncError("");
      closeEditor();
    } catch (saveError) {
      setError(saveError instanceof Error ? saveError.message : "Could not save the workout.");
    } finally {
      setSaving(false);
    }
  }

  async function deleteWorkout() {
    if (!selectedDate) return;
    const token = window.localStorage.getItem(AUTH_TOKEN_KEY);
    if (!token) {
      setError("Your session has expired. Sign in again before deleting.");
      return;
    }
    setSaving(true);
    try {
      await deleteRunningWorkout(selectedDate, token);
      setWorkouts((current) => {
        const next = { ...current };
        delete next[selectedDate];
        return next;
      });
      setSyncError("");
      closeEditor();
    } catch (deleteError) {
      setError(deleteError instanceof Error ? deleteError.message : "Could not delete the workout.");
    } finally {
      setSaving(false);
    }
  }

  const monthLabel = new Intl.DateTimeFormat("en", { month: "long", year: "numeric" }).format(month);
  const selectedLabel = selectedDate
    ? new Intl.DateTimeFormat("en", { weekday: "long", day: "numeric", month: "long" }).format(
        new Date(`${selectedDate}T12:00:00`),
      )
    : "";

  return (
    <section className="running-workspace">
      <header className="running-header">
        <div>
          <p className="eyebrow">Additional · Running log</p>
          <h2>Training calendar</h2>
          <p className="running-intro">A monthly view of load, rhythm and recovery. Select any day to add a run.</p>
        </div>
        <button className="today-button" type="button" onClick={() => {
          const today = new Date();
          setMonth(new Date(today.getFullYear(), today.getMonth(), 1));
        }}>
          Today
        </button>
      </header>

      <div className="running-summary" aria-label="Monthly summary">
        <article><span>Distance</span><strong>{totals.totalDistance.toFixed(1)}</strong><small>km this month</small></article>
        <article><span>Sessions</span><strong>{monthWorkouts.length}</strong><small>completed runs</small></article>
        <article><span>Avg. pace</span><strong>{totals.averagePace}</strong><small>min / km</small></article>
        <article><span>Avg. heart rate</span><strong>{totals.averageHeartRate || "—"}</strong><small>bpm</small></article>
      </div>

      <article className="calendar-card">
        <div className="calendar-toolbar">
          <div className="month-control">
            <button type="button" aria-label="Previous month" onClick={() => setMonth((value) => new Date(value.getFullYear(), value.getMonth() - 1, 1))}>←</button>
            <h3>{monthLabel}</h3>
            <button type="button" aria-label="Next month" onClick={() => setMonth((value) => new Date(value.getFullYear(), value.getMonth() + 1, 1))}>→</button>
          </div>
          <div className="workout-legend" aria-label="Workout types">
            {WORKOUT_TYPES.map((item) => <span key={item.value}><i className={`legend-dot type-${item.value}`} />{item.label}</span>)}
          </div>
        </div>

        <div className="calendar-scroll">
          <div className="calendar-grid calendar-weekdays">
            {WEEKDAYS.map((day) => <div key={day}>{day}</div>)}
          </div>
          <div className="calendar-grid calendar-days">
            {days.map((date) => {
              const key = dateKey(date);
              const workout = workouts[key];
              const isOutside = date.getMonth() !== month.getMonth();
              const isToday = key === dateKey(new Date());
              return (
                <button
                  type="button"
                  disabled={!loaded || saving}
                  className={`calendar-day${isOutside ? " day-outside" : ""}${isToday ? " day-today" : ""}${workout ? ` has-workout type-${workout.type}` : ""}`}
                  key={key}
                  onClick={() => openEditor(key)}
                  aria-label={`${key}${workout ? `, ${WORKOUT_TYPES.find((item) => item.value === workout.type)?.label} run` : ", add workout"}`}
                >
                  <span className="day-number">{date.getDate()}</span>
                  {workout ? (
                    <span className="workout-data">
                      <strong>{workout.distance} km</strong>
                      <span><b>{workout.pace}</b> /km</span>
                      <span><b>{workoutDuration(workout)}</b> total</span>
                      <span><b>{workout.heartRate}</b> bpm</span>
                    </span>
                  ) : <span className="add-run">+ add run</span>}
                </button>
              );
            })}
          </div>
        </div>
      </article>

      <p className={`storage-note${syncError ? " storage-note-error" : ""}`} role={syncError ? "alert" : undefined}>
        {!loaded
          ? "Loading training history from your account…"
          : syncError || "Training data is saved securely to your account."}
      </p>

      <dialog className="workout-dialog" ref={dialogRef} onClose={() => setError("")}>
        <form method="dialog" onSubmit={saveWorkout}>
          <div className="dialog-heading">
            <div><p className="eyebrow">Training details</p><h3>{selectedLabel}</h3></div>
            <button className="dialog-close" type="button" aria-label="Close" onClick={closeEditor} disabled={saving}>×</button>
          </div>

          <fieldset className="type-picker">
            <legend>Workout type</legend>
            {WORKOUT_TYPES.map((item) => (
              <label className={`type-choice type-${item.value}${type === item.value ? " selected" : ""}`} key={item.value}>
                <input type="radio" name="workout-type" value={item.value} checked={type === item.value} onChange={() => setType(item.value)} />
                <i />{item.label}
              </label>
            ))}
          </fieldset>

          <div className="workout-fields">
            <label><span>Distance</span><div><input inputMode="decimal" placeholder="10.0" value={distance} onChange={(event) => setDistance(event.target.value)} autoFocus /><small>km</small></div></label>
            <label><span>Pace</span><div><input inputMode="numeric" placeholder="5:25" value={pace} onChange={(event) => {
              setPace(event.target.value);
              if (calculatedFrom === "duration") setCalculatedFrom(undefined);
            }} /><small>min/km</small></div></label>
            <label><span>Total time</span><div><input inputMode="numeric" placeholder="54:10" value={duration} onChange={(event) => {
              setDuration(event.target.value);
              if (calculatedFrom === "pace") setCalculatedFrom(undefined);
            }} /><small>h:mm:ss</small></div></label>
            <label><span>Average heart rate</span><div><input inputMode="numeric" placeholder="145" value={heartRate} onChange={(event) => setHeartRate(event.target.value)} /><small>bpm</small></div></label>
          </div>

          <p className="calculation-preview">{calculationPreview}</p>

          {error ? <p className="form-error" role="alert">{error}</p> : null}
          <div className="dialog-actions">
            {selectedDate && workouts[selectedDate] ? <button className="delete-button" type="button" onClick={deleteWorkout} disabled={saving}>Delete run</button> : <span />}
            <div><button className="cancel-button" type="button" onClick={closeEditor} disabled={saving}>Cancel</button><button className="save-button" type="submit" disabled={saving}>{saving ? "Saving…" : "Save workout"}</button></div>
          </div>
        </form>
      </dialog>
    </section>
  );
}
