# Runbook

## Goal

This runbook is for working with the new migration contour while keeping legacy Streamlit available as fallback.

## 1. Prepare environment

Create `.env` from `.env.example` and fill:

- `PERF_CLIENT_ID`
- `PERF_CLIENT_SECRET`
- `SELLER_CLIENT_ID`
- `SELLER_API_KEY`
- `SECRET_KEY`
- `API_BASE_URL`
- `NEXT_PUBLIC_API_BASE_URL`

## 2. Create database tables

Temporary bootstrap command:

```bash
python -c "import sys; sys.path.insert(0, 'backend'); from app.db.bootstrap import create_all; create_all()"
```

## 3. Seed first admin user

```bash
python backend/scripts/seed_admin.py --email admin@example.com --password change-me --full-name Admin
```

## 4. Run backend locally

```bash
pip install -r backend/requirements.txt
uvicorn app.main:app --app-dir backend --reload
```

## 5. Run frontend locally

```bash
cd frontend
npm install
npm run dev
```

## 6. Run full stack through Docker

```bash
docker compose up --build
```

## 7. Validate first flows

Check:

- `GET /api/health`
- login through frontend
- campaigns dashboard loads
- bid audit loads
- `apply bid` writes to the shared bid log
- stocks snapshot loads
- storage risk snapshot loads
- finance summary loads

Optional automated smoke:

```bash
python backend/scripts/live_smoke.py --backend http://127.0.0.1:8200/api --frontend http://127.0.0.1:3200
```

## 8. Validate campaign parity

```bash
python backend/scripts/campaign_report_parity.py --company default --date-from 2026-03-18 --date-to 2026-03-24 --json
```

Expected:

- `grand_total_match=true`
- `rows_match=true`

## 9. Fallback rule

If any migrated flow is broken or produces inconsistent data, use the legacy Streamlit contour as the operational fallback until the issue is resolved.
