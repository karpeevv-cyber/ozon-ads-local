# Architecture Notes

## Product contours

### Legacy contour

- current Streamlit UI
- file-based state and cache
- direct calls to Ozon APIs from UI-oriented modules

### New contour

- `backend` as the system of record
- `frontend` as the product UI
- database-backed state
- background jobs for refresh and reporting

## Initial migration principle

The first migration target is not visual parity. It is separation of concerns:

1. integrations
2. business logic
3. persistence
4. API
5. UI

This reduces rewrite risk and preserves the ability to compare new results against the legacy system.
