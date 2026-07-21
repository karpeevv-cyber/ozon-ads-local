"use client";

import { FormEvent, useEffect, useMemo, useRef, useState } from "react";

type WorkoutType = "base" | "intervals" | "tempo" | "long";

type Workout = {
  date: string;
  distance: number;
  pace: string;
  heartRate: number;
  type: WorkoutType;
};

const STORAGE_KEY = "marketrix-running-workouts-v1";

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
  const [minutes, seconds] = pace.split(":").map(Number);
  return Number.isFinite(minutes) && Number.isFinite(seconds) ? minutes * 60 + seconds : 0;
}

function secondsToPace(value: number) {
  const minutes = Math.floor(value / 60);
  const seconds = Math.round(value % 60);
  return `${minutes}:${String(seconds).padStart(2, "0")}`;
}

export function RunningCalendar() {
  const [month, setMonth] = useState(() => {
    const today = new Date();
    return new Date(today.getFullYear(), today.getMonth(), 1);
  });
  const [workouts, setWorkouts] = useState<Record<string, Workout>>({});
  const [loaded, setLoaded] = useState(false);
  const [selectedDate, setSelectedDate] = useState<string | null>(null);
  const [distance, setDistance] = useState("");
  const [pace, setPace] = useState("");
  const [heartRate, setHeartRate] = useState("");
  const [type, setType] = useState<WorkoutType>("base");
  const [error, setError] = useState("");
  const dialogRef = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    try {
      const stored = window.localStorage.getItem(STORAGE_KEY);
      if (stored) setWorkouts(JSON.parse(stored) as Record<string, Workout>);
    } catch {
      // A malformed or unavailable local store should not block the calendar.
    } finally {
      setLoaded(true);
    }
  }, []);

  useEffect(() => {
    if (!loaded) return;
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(workouts));
  }, [loaded, workouts]);

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

  function openEditor(key: string) {
    const workout = workouts[key];
    setSelectedDate(key);
    setDistance(workout ? String(workout.distance) : "");
    setPace(workout?.pace ?? "");
    setHeartRate(workout ? String(workout.heartRate) : "");
    setType(workout?.type ?? "base");
    setError("");
    dialogRef.current?.showModal();
  }

  function closeEditor() {
    dialogRef.current?.close();
    setError("");
  }

  function saveWorkout(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedDate) return;
    const numericDistance = Number(distance.replace(",", "."));
    const numericHeartRate = Number(heartRate);
    const paceMatch = pace.match(/^(\d{1,2}):([0-5]\d)$/);
    if (!numericDistance || numericDistance <= 0) {
      setError("Enter a distance greater than zero.");
      return;
    }
    if (!paceMatch) {
      setError("Use the pace format mm:ss, for example 5:25.");
      return;
    }
    if (!numericHeartRate || numericHeartRate < 30 || numericHeartRate > 240) {
      setError("Heart rate must be between 30 and 240 bpm.");
      return;
    }
    const nextWorkouts = {
      ...workouts,
      [selectedDate]: {
        date: selectedDate,
        distance: Math.round(numericDistance * 100) / 100,
        pace,
        heartRate: Math.round(numericHeartRate),
        type,
      },
    };
    setWorkouts(nextWorkouts);
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(nextWorkouts));
    closeEditor();
  }

  function deleteWorkout() {
    if (!selectedDate) return;
    const nextWorkouts = { ...workouts };
    delete nextWorkouts[selectedDate];
    setWorkouts(nextWorkouts);
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(nextWorkouts));
    closeEditor();
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
                      <span><b>{workout.heartRate}</b> bpm</span>
                    </span>
                  ) : <span className="add-run">+ add run</span>}
                </button>
              );
            })}
          </div>
        </div>
      </article>

      <p className="storage-note">Training data is saved automatically in this browser.</p>

      <dialog className="workout-dialog" ref={dialogRef} onClose={() => setError("")}>
        <form method="dialog" onSubmit={saveWorkout}>
          <div className="dialog-heading">
            <div><p className="eyebrow">Training details</p><h3>{selectedLabel}</h3></div>
            <button className="dialog-close" type="button" aria-label="Close" onClick={closeEditor}>×</button>
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
            <label><span>Pace</span><div><input inputMode="numeric" placeholder="5:25" value={pace} onChange={(event) => setPace(event.target.value)} /><small>min/km</small></div></label>
            <label><span>Average heart rate</span><div><input inputMode="numeric" placeholder="145" value={heartRate} onChange={(event) => setHeartRate(event.target.value)} /><small>bpm</small></div></label>
          </div>

          {error ? <p className="form-error" role="alert">{error}</p> : null}
          <div className="dialog-actions">
            {selectedDate && workouts[selectedDate] ? <button className="delete-button" type="button" onClick={deleteWorkout}>Delete run</button> : <span />}
            <div><button className="cancel-button" type="button" onClick={closeEditor}>Cancel</button><button className="save-button" type="submit">Save workout</button></div>
          </div>
        </form>
      </dialog>
    </section>
  );
}
