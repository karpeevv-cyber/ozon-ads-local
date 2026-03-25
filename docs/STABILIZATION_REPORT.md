# Stabilization Report

## Scope

This report reflects what has actually been verified in the current workspace session.

It does not claim that every runtime flow has been executed end-to-end. It separates:

- checks completed in this environment
- checks prepared in code but not yet executed here

## Verified In This Session

### Code integrity

- `python -m compileall backend/app backend/scripts` passes
- all added backend API modules compile
- all added backend service modules compile
- parity script compiles
- admin seed script compiles

### Migration structure

- legacy contour remains untouched as the fallback runtime
- new repository structure exists for backend, frontend, docs, infra, and legacy
- runbook, checklist, parity docs, and status docs are present

### Backend runtime smoke

- backend dependencies were installed into the local virtual environment
- FastAPI app was loaded through `TestClient` successfully
- `GET /api/health` returned `200`
- `GET /api/campaigns/companies` returned `200`
- `GET /api/auth/me` without a bearer token returned `401`
- DB tables were created locally through `app.db.bootstrap.create_all()`
- first admin user was seeded locally through `backend/scripts/seed_admin.py`
- `POST /api/auth/login` succeeded with the seeded admin user
- `GET /api/auth/me` succeeded with the issued bearer token
- key backend business endpoints were exercised successfully for the `default` company:
  - `campaigns/running`
  - `campaigns/report`
  - `bids/recent`
  - `bids/comments`
  - `stocks/snapshot`
  - `storage/snapshot`
  - `finance/summary`
  - `trends/snapshot`
  - `unit-economics/summary`
  - `unit-economics/products`
- admin-protected `PUT /api/unit-economics/products` succeeded in runtime smoke
- the temporary test override created during validation was removed from both DB state and CSV mirror after the check
- `storage` snapshot fallback import was exercised and now restores a backend-owned cache file under `backend/data`
- `trends` snapshot cache was exercised and now writes to `backend/data`

### Frontend runtime smoke

- frontend dependencies were installed with `npm install`
- a JSX build error in `BidAuditPanel.tsx` was fixed
- `next` was upgraded from `15.4.6` to `15.5.14` to remove known vulnerabilities
- `npm audit` returned `0 vulnerabilities`
- `npm run build` completed successfully with `Next.js 15.5.14`
- a live backend process was started on `http://127.0.0.1:8200`
- a live standalone frontend process was started on `http://127.0.0.1:3200`
- `GET /api/health` returned `200` through the live backend process
- the frontend root page returned `200` through the live standalone process after rebuild with corrected API env
- the standalone runtime blocker was traced to Windows `cmd` env formatting: a trailing space in `API_BASE_URL` produced `404`, and `next start` was invalid because the app uses `output: standalone`
- `backend/scripts/live_smoke.py --backend http://127.0.0.1:8200/api --frontend http://127.0.0.1:3200 --json` passed with `17/17`

### Legacy parity

- `backend/scripts/campaign_report_parity.py --company default --date-from 2026-03-18 --date-to 2026-03-24 --json` returned:
  - `grand_total_match=true`
  - `rows_match=true`
  - `mismatch_count=0`

### Implemented backend API surface

- `health`
- `auth`
- `campaigns`
- `bids`
- `stocks`
- `storage`
- `finance`
- `trends`
- `unit_economics`

## Not Yet Verified In This Session

### Runtime boot

- backend app exercised in-process through `FastAPI TestClient` and a live `uvicorn` process
- frontend process started with installed dependencies and a live standalone process
- docker compose booted successfully
- nginx proxy routing verified

### Auth runtime

- browser login flow through the real frontend
- auth persistence across browser refresh

### Business flows

- campaigns dashboard loaded from live API in browser
- bid apply executed against a known campaign/SKU
- bid write confirmed through the new backend-owned log path
- browser auth flow exercised through the real frontend
- full live click-through in a real browser is still pending, but the automated live smoke now covers backend health, auth, key API reads, and frontend root render

## Current Risk Notes

- the new contour is functionally broad, and runtime validation has started, but browser and compose coverage still lag behind implementation
- several modules still keep legacy filesystem fallback paths for compatibility, even though primary writes have started moving to `backend/data` and DB-backed storage
- browser-level click-through verification has not been exercised in this session, even though the live frontend root page now renders successfully
- production cutover is not close enough to justify switching traffic
- local auth smoke used SQLite dev state, not the target PostgreSQL containerized stack
- Docker is not installed in the current workspace environment, so compose/nginx validation is blocked here
- Windows process launch quirks caused some false starts during runtime validation: `next start` is invalid for `output: standalone`, and `cmd set` syntax can silently inject trailing spaces into env values

## Recommended Next Stabilization Actions

1. Start the backend through `uvicorn` against the intended local environment.
2. Run the Next.js app locally and verify browser login plus dashboard loading.
3. Run the checklist in `docs/CHECKLIST.md`.
4. Validate docker compose boot for `postgres + redis + backend + frontend + nginx` in an environment with Docker installed.
5. Continue with `trends` and `unit_economics` once browser/runtime validation is in place.
