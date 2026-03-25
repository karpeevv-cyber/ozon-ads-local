# Backend

Target backend stack:

- FastAPI
- PostgreSQL
- Redis
- Celery

Planned application layout:

- `app/api`
- `app/core`
- `app/db`
- `app/models`
- `app/repositories`
- `app/schemas`
- `app/services`
- `app/tasks`
- `app/workers`

The backend will become the single source of truth for integrations, business logic, and persistent state.
