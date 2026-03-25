# Migration Status

## Current new-stack coverage

The new `FastAPI + Next.js` contour already includes these working modules:

- `auth`
- `campaigns`
- `bids`
- `stocks`
- `storage`
- `finance`
- `trends`
- `unit_economics`

## Current backend endpoints

- `/api/health`
- `/api/auth/login`
- `/api/auth/me`
- `/api/campaigns/companies`
- `/api/campaigns/running`
- `/api/campaigns/report`
- `/api/bids/recent`
- `/api/bids/comments`
- `/api/bids/tests`
- `/api/bids/apply`
- `/api/stocks/snapshot`
- `/api/storage/snapshot`
- `/api/finance/summary`
- `/api/trends/snapshot`
- `/api/unit-economics/summary`
- `/api/unit-economics/products`
- `/api/unit-economics/products` `PUT`

## What is still legacy-only

- scheduled finance reporting and Telegram delivery
- storage refresh pipeline in the new backend
- stocks review workflow and approvals persistence in the new backend
- full DB-backed replacement for all remaining file caches and mirrors
- browser click-through validation of the new frontend contour
- containerized runtime validation with Docker/Compose

## Migration quality level

### Already achieved

- legacy Streamlit remains untouched as fallback
- new stack has product UI, auth baseline, and multiple working data modules
- bid changes can already be written through the new backend
- campaign report parity tooling exists
- `campaigns`, `bids`, `stocks`, `storage`, `finance`, `trends`, and `unit_economics` are available in the new contour
- several fallback file-state paths now use `backend/data` as the primary new-stack storage
- `trends`, `storage`, `unit economics`, and bid logs are no longer legacy-root-first in the new backend
- automated live smoke covers backend health, auth, key API reads, and frontend root render
- the Docker contour now uses a production standalone frontend and persists backend-owned file state via `backend_data`

### Still required before cutover

- run the parity checks on real production-like ranges
- move more state off legacy files
- add smoke tests and operational checks
- harden auth and secret handling for production
- validate browser click-through and container boot
