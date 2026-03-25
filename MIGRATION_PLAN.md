# Migration Plan

## Goals

- Keep the current Streamlit application working during the migration.
- Build the new product in parallel on `FastAPI + Next.js`.
- Migrate by domain and by layer, not by rewriting everything at once.
- Preserve rollback capability until the new stack reaches functional parity.

## Current State

The current repository contains one working Streamlit application with several domain areas already visible in code:

- `campaigns` and ads reporting
- `bids` and bid change logging
- `finance`
- `stocks`
- `storage`
- `trends`
- `unit economics`

The main technical problems in the current codebase are:

- UI, business logic, API clients, caching, and persistence are mixed together
- state is stored in local `csv` and `pkl` files
- there is no API boundary between frontend and backend
- the app is optimized for a single-user or small internal workflow

## Migration Rules

1. Legacy Streamlit remains runnable at all times.
2. New code is added in parallel and does not break the legacy flow.
3. Existing business logic is extracted and reused where possible.
4. New storage goes to a database, not to new `csv` or `pkl` files.
5. Production traffic stays on Streamlit until the new stack is validated.

## Target Architecture

### Repository layout

```text
backend/
  app/
    api/
    core/
    db/
    models/
    repositories/
    schemas/
    services/
    tasks/
    workers/
frontend/
  src/
    app/
    features/
    entities/
    shared/
legacy/
  streamlit/
docs/
infra/
```

### Backend domains

- `auth`
- `organizations`
- `integrations/ozon_ads`
- `integrations/ozon_seller`
- `campaigns`
- `bids`
- `analytics`
- `finance`
- `stocks`
- `storage`
- `trends`
- `unit_economics`
- `reports`
- `tasks`

### Infrastructure

- `FastAPI`
- `PostgreSQL`
- `Redis`
- `Celery` for background jobs
- `Next.js`
- `Nginx`
- `Docker Compose` for local/server bootstrap

## Proposed Mapping From Current Files

### Legacy UI files

- `ui.py` -> legacy app entrypoint, source for screen-by-screen migration
- `ui_finance_tab.py` -> `finance`
- `ui_stocks_new_tab.py`, `ui_stocks_tab.py` -> `stocks`
- `ui_storage_tab.py` -> `storage`
- `ui_trends_tab.py` -> `trends`
- `ui_unit_economics_tab.py`, `ui_unit_economics_products_tab.py` -> `unit_economics`
- `ui_tabs_misc.py` -> low priority informational content

### Integration and service candidates

- `clients_ads.py` -> `backend/app/services/integrations/ozon_ads`
- `clients_seller.py` -> `backend/app/services/integrations/ozon_seller`
- `seller_products.py` -> seller catalog/report service
- `send_finance_yesterday.py` -> scheduled reporting task

### Domain logic candidates

- `bid_changes.py`, `bid_ui_helpers.py` -> `bids`
- `report.py`, parts of `ui_data.py` -> `analytics` and `campaigns`
- `trend_data.py`, `trend_scoring.py`, `trend_sources.py`, `trend_external.py` -> `trends`
- `ui_helpers.py` -> split into config, caching, and persistence adapters

## Migration Phases

### Phase 1. Audit and structure

- document target architecture
- create new repository structure without touching legacy runtime
- mark legacy code explicitly

### Phase 2. Backend foundation

- bootstrap `FastAPI`
- add app config and environment loading
- add healthcheck and base routing
- add database and migration tooling
- add Redis and Celery skeleton

### Phase 3. Shared backend services

- extract Ozon clients into backend service modules
- extract reusable calculation logic from UI modules
- isolate filesystem cache usage behind adapters

### Phase 4. Database migration

- define core entities:
  - users
  - organizations
  - marketplace credentials
  - campaigns
  - campaign products
  - bid changes
  - campaign comments
  - analytics snapshots
  - stock snapshots
  - storage snapshots
  - trend snapshots
- replace active state writes to `csv` and `pkl`

### Phase 5. Frontend foundation

- bootstrap `Next.js`
- define app shell, auth shell, and route structure
- add API client, error handling, and shared table/chart primitives

### Phase 6. First end-to-end slice

The first migrated scenario should be:

- organization selection
- campaign list for period
- summary metrics
- campaign details

Reason:

- it is central to the product
- it exercises both Ozon integrations
- it creates the API contract used by later modules

### Phase 7. Domain-by-domain migration

Suggested order:

1. `campaigns` and summary analytics
2. `bids`
3. `finance`
4. `stocks`
5. `storage`
6. `trends`
7. `unit_economics`
8. scheduled reports and exports

### Phase 8. Stabilization and cutover

- parity checks against Streamlit
- smoke tests
- structured logging
- monitoring and error tracking
- partial internal rollout
- production switch with fallback period

## Definition of Done For Cutover

The new stack can replace Streamlit only when:

- core user flows are available in the new UI
- data matches legacy results within agreed tolerance
- bid changes and comments are safely persisted
- auth and access control are active
- background refresh jobs are stable
- rollback to legacy remains possible during the transition window

## Immediate Execution Order

1. Create the new repository structure.
2. Bootstrap backend and frontend applications.
3. Preserve current files as legacy runtime.
4. Extract Ozon integrations and reusable services.
5. Implement the first end-to-end campaigns flow.
