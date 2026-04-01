# PROJECT GUIDE

This file is the default orientation point for any new task in this repository.

## 1) What this repository contains

The repo has **two global project versions in parallel**:

1. `legacy` contour (current operational fallback): Streamlit-based app logic that still runs from repo root files.
2. `new` contour (migration target): `backend` (FastAPI) + `frontend` (Next.js).

Migration is incremental. Legacy must stay runnable until full parity and cutover.

## 2) First files to read in a new conversation

Use this order:

1. `PROJECT_GUIDE.md` (this file)
2. `README.md`
3. `docs/STATUS.md` (actual coverage and gaps)
4. `docs/RUNBOOK.md` (how to run/check)
5. `MIGRATION_PLAN.md` (target architecture and mapping)

If the task is domain-specific, then jump to domain modules listed below.

## 3) Version A: Legacy contour (Streamlit fallback)

Important: `legacy/streamlit` is currently a placeholder boundary. The active legacy runtime files are still in repository root.

### Legacy entrypoints and core files

1. `ui.py` - main Streamlit entrypoint.
2. `ui_*` modules - tabs and UI-specific flows (`finance`, `stocks`, `storage`, `trends`, `unit economics`, etc.).
3. `clients_ads.py`, `clients_seller.py` - direct Ozon API clients used by legacy flows.
4. `bid_changes.py`, `report.py`, `trend_*` - business/domain logic used by Streamlit screens.
5. Root `*.csv` and `*.pkl` artifacts - historical file-based state/cache used by legacy flows.

### Legacy rule

Do not break legacy behavior while implementing migration work. If new contour is unstable, legacy is the fallback.

## 4) Version B: New contour (FastAPI + Next.js)

### Backend (`backend/`)

Primary structure:

- `backend/app/api` - HTTP routes.
- `backend/app/services` - domain services and integration adapters.
- `backend/app/services/integrations` - Ozon integration logic.
- `backend/app/models`, `schemas`, `db` - persistence/data contracts.
- `backend/scripts` - operational scripts (`seed_admin.py`, `live_smoke.py`, `campaign_report_parity.py`).
- `backend/data` - backend-owned runtime file state during migration.

Entrypoint:

- `backend/app/main.py`

### Frontend (`frontend/`)

Primary structure:

- `frontend/src/app` - app shell and routes.
- `frontend/src/features/*` - domain feature screens/components.
- `frontend/src/shared/api` - API client and types.
- `frontend/src/shared/ui` - shared UI shell/components.

### Current new-stack API surface (high-level)

See `docs/STATUS.md` for current truth. Main modules already present:

- auth
- campaigns
- bids
- stocks
- storage
- finance
- trends
- unit economics

## 5) Run commands

### Local (new contour)

```bash
pip install -r backend/requirements.txt
uvicorn app.main:app --app-dir backend --reload
```

```bash
cd frontend
npm install
npm run dev
```

Expected API base for frontend:

```bash
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000/api
```

### Local infra (containers)

```bash
docker compose up --build
```

Main ports:

- `8000` backend
- `3000` frontend
- `80` nginx
- `5432` postgres
- `6379` redis

## 6) Verification checklist after changes

1. `GET /api/health` responds.
2. Frontend loads and authenticates.
3. Affected domain endpoint works (campaigns/bids/stocks/storage/finance/trends/unit-economics).
4. If logic changed, run parity/smoke scripts from `backend/scripts`.
5. If parity mismatch or regression appears, keep/restore legacy fallback usage.

## 7) Where to implement new work

Use this default routing:

1. New API/domain logic -> `backend/app/services` + `backend/app/api`.
2. New UI behavior for migrated screens -> `frontend/src/features/...`.
3. Legacy-only urgent fix -> root Streamlit modules (`ui_*`, `clients_*`, etc.) with minimal blast radius.

Avoid adding new long-term state to root-level `csv/pkl`; prefer backend-managed storage paths and DB-oriented flow.

## 8) Migration safety constraints

1. Legacy fallback must remain runnable.
2. New code should not silently change legacy results without parity checks.
3. For Ozon integration changes, verify endpoint versions and deprecation windows before merging.
4. Keep migration changes incremental and domain-scoped.

## 9) Conversation shortcut

For new chats, use:

`Read PROJECT_GUIDE.md first, then proceed with task X.`

That is enough to orient work across both global versions of the project.
