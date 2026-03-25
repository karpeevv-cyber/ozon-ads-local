# Ozon Ads Migration Workspace

This repository now contains two parallel product contours:

- `legacy/streamlit` for the current Streamlit application
- `backend` for the new FastAPI backend
- `frontend` for the new Next.js frontend

The migration strategy is documented in [MIGRATION_PLAN.md](C:\Users\User\ozon-ads-local\MIGRATION_PLAN.md).
Current execution status is tracked in [STATUS.md](C:\Users\User\ozon-ads-local\docs\STATUS.md).
Operational steps are in [RUNBOOK.md](C:\Users\User\ozon-ads-local\docs\RUNBOOK.md).

## Repository Areas

- `legacy/streamlit`: legacy runtime and compatibility layer
- `backend`: new backend application and services
- `frontend`: new frontend application
- `infra`: deployment and infrastructure files
- `docs`: architecture and migration notes

## Current Rule

The legacy Streamlit application remains the production-safe fallback until the new stack reaches functional parity.
