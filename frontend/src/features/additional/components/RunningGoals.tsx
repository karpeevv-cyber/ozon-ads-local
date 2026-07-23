"use client";

import { CSSProperties, FormEvent, useEffect, useRef, useState } from "react";

import {
  createRunningGoal,
  deleteRunningGoal,
  getRunningGoals,
  updateRunningGoal,
} from "@/shared/api/client";
import { RunningGoalPayload, RunningGoalRecord } from "@/shared/api/types";


const AUTH_TOKEN_KEY = "ozon_ads_token";

function todayKey() {
  const today = new Date();
  const year = today.getFullYear();
  const month = String(today.getMonth() + 1).padStart(2, "0");
  const day = String(today.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function formatNumber(value: number) {
  return new Intl.NumberFormat("en", { maximumFractionDigits: 2 }).format(value);
}

function formatDate(value: string) {
  return new Intl.DateTimeFormat("en", { day: "numeric", month: "short", year: "numeric" }).format(
    new Date(`${value}T12:00:00`),
  );
}

export function RunningGoals({ refreshKey }: { refreshKey: number }) {
  const [goals, setGoals] = useState<RunningGoalRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [loadError, setLoadError] = useState("");
  const [formError, setFormError] = useState("");
  const [editingGoal, setEditingGoal] = useState<RunningGoalRecord | null>(null);
  const [title, setTitle] = useState("");
  const [targetValue, setTargetValue] = useState("");
  const [startDate, setStartDate] = useState(todayKey);
  const dialogRef = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    let cancelled = false;

    async function loadGoals() {
      const token = window.localStorage.getItem(AUTH_TOKEN_KEY);
      if (!token) {
        if (!cancelled) {
          setLoadError("Your session has expired. Sign in again to load goals.");
          setLoading(false);
        }
        return;
      }
      try {
        const rows = await getRunningGoals(token);
        if (!cancelled) {
          setGoals(rows);
          setLoadError("");
        }
      } catch (error) {
        if (!cancelled) {
          setLoadError(error instanceof Error ? error.message : "Could not load goals.");
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    void loadGoals();
    return () => {
      cancelled = true;
    };
  }, [refreshKey]);

  function openGoalEditor(goal?: RunningGoalRecord) {
    setEditingGoal(goal ?? null);
    setTitle(goal?.title ?? "");
    setTargetValue(goal ? String(goal.target_value) : "");
    setStartDate(goal?.start_date ?? todayKey());
    setFormError("");
    dialogRef.current?.showModal();
  }

  function closeGoalEditor() {
    dialogRef.current?.close();
    setFormError("");
  }

  async function saveGoal(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const numericTarget = Number(targetValue.replace(",", "."));
    if (!title.trim()) {
      setFormError("Enter a goal name.");
      return;
    }
    if (!Number.isFinite(numericTarget) || numericTarget <= 0) {
      setFormError("Target distance must be greater than zero.");
      return;
    }
    if (!startDate) {
      setFormError("Choose a start date.");
      return;
    }
    const token = window.localStorage.getItem(AUTH_TOKEN_KEY);
    if (!token) {
      setFormError("Your session has expired. Sign in again before saving.");
      return;
    }
    const payload: RunningGoalPayload = {
      title: title.trim(),
      metric_type: "distance",
      target_value: Math.round(numericTarget * 100) / 100,
      start_date: startDate,
    };
    setSaving(true);
    try {
      const saved = editingGoal
        ? await updateRunningGoal(editingGoal.id, payload, token)
        : await createRunningGoal(payload, token);
      setGoals((current) =>
        editingGoal
          ? current.map((goal) => (goal.id === saved.id ? saved : goal))
          : [saved, ...current],
      );
      setLoadError("");
      closeGoalEditor();
    } catch (error) {
      setFormError(error instanceof Error ? error.message : "Could not save the goal.");
    } finally {
      setSaving(false);
    }
  }

  async function removeGoal() {
    if (!editingGoal) return;
    const token = window.localStorage.getItem(AUTH_TOKEN_KEY);
    if (!token) {
      setFormError("Your session has expired. Sign in again before deleting.");
      return;
    }
    setSaving(true);
    try {
      await deleteRunningGoal(editingGoal.id, token);
      setGoals((current) => current.filter((goal) => goal.id !== editingGoal.id));
      closeGoalEditor();
    } catch (error) {
      setFormError(error instanceof Error ? error.message : "Could not delete the goal.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <section className="goals-section" aria-labelledby="running-goals-title">
      <div className="goals-heading">
        <div>
          <p className="eyebrow">Running objectives</p>
          <h2 id="running-goals-title">Goals in motion</h2>
          <p>Each run from the selected start date moves the distance counter forward.</p>
        </div>
        <button className="add-goal-button" type="button" onClick={() => openGoalEditor()}>
          <span aria-hidden="true">＋</span> New goal
        </button>
      </div>

      {loading ? <p className="goals-state">Loading goals…</p> : null}
      {!loading && loadError ? <p className="goals-state goals-state-error" role="alert">{loadError}</p> : null}
      {!loading && !loadError && goals.length === 0 ? (
        <button className="goal-empty-card" type="button" onClick={() => openGoalEditor()}>
          <span className="goal-empty-mark">◎</span>
          <span><strong>Set your first distance goal</strong><small>Choose a start date and a finish line.</small></span>
          <b>＋</b>
        </button>
      ) : null}

      {goals.length > 0 ? (
        <div className="goals-grid">
          {goals.map((goal) => {
            const ringProgress = Math.min(100, Math.max(0, goal.progress_percent));
            return (
              <article className={`goal-card${goal.completed ? " goal-complete" : ""}`} key={goal.id}>
                <div
                  className="goal-progress-ring"
                  style={{ "--goal-progress": `${ringProgress * 3.6}deg` } as CSSProperties}
                  aria-label={`${formatNumber(goal.progress_percent)} percent complete`}
                >
                  <span><strong>{formatNumber(goal.progress_percent)}%</strong><small>complete</small></span>
                </div>
                <div className="goal-card-copy">
                  <div className="goal-card-meta">
                    <span>Distance</span>
                    {goal.completed ? <b>Completed</b> : <b>Active</b>}
                  </div>
                  <h3>{goal.title}</h3>
                  <p><strong>{formatNumber(goal.current_value)}</strong> / {formatNumber(goal.target_value)} km</p>
                  <small>Counting since {formatDate(goal.start_date)}</small>
                </div>
                <button className="goal-edit-button" type="button" onClick={() => openGoalEditor(goal)} aria-label={`Edit goal ${goal.title}`}>
                  Edit
                </button>
              </article>
            );
          })}
        </div>
      ) : null}

      <dialog className="workout-dialog goal-dialog" ref={dialogRef} onClose={() => setFormError("")}>
        <form method="dialog" onSubmit={saveGoal}>
          <div className="dialog-heading">
            <div><p className="eyebrow">Distance goal</p><h3>{editingGoal ? "Edit the finish line" : "Set a new finish line"}</h3></div>
            <button className="dialog-close" type="button" aria-label="Close" onClick={closeGoalEditor} disabled={saving}>×</button>
          </div>

          <div className="goal-fields">
            <label>
              <span>Goal name</span>
              <input value={title} onChange={(event) => setTitle(event.target.value)} placeholder="Run 100 km" autoFocus />
            </label>
            <label>
              <span>What we count</span>
              <select value="distance" disabled aria-label="Goal metric">
                <option value="distance">Distance</option>
              </select>
              <small>More goal types can be added here later.</small>
            </label>
            <label>
              <span>Target distance</span>
              <div><input inputMode="decimal" value={targetValue} onChange={(event) => setTargetValue(event.target.value)} placeholder="100" /><small>km</small></div>
            </label>
            <label>
              <span>Start date</span>
              <input type="date" value={startDate} onChange={(event) => setStartDate(event.target.value)} />
            </label>
          </div>

          {formError ? <p className="form-error" role="alert">{formError}</p> : null}
          <div className="dialog-actions">
            {editingGoal ? <button className="delete-button" type="button" onClick={removeGoal} disabled={saving}>Delete goal</button> : <span />}
            <div>
              <button className="cancel-button" type="button" onClick={closeGoalEditor} disabled={saving}>Cancel</button>
              <button className="save-button" type="submit" disabled={saving}>{saving ? "Saving…" : "Save goal"}</button>
            </div>
          </div>
        </form>
      </dialog>
    </section>
  );
}
