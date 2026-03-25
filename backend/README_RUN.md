# Backend Run

## Local run

```bash
pip install -r backend/requirements.txt
uvicorn app.main:app --app-dir backend --reload
```

API base:

- `http://localhost:8000/api/health`
- `http://localhost:8000/api/campaigns/companies`
- `http://localhost:8000/api/campaigns/running`

The current endpoints are only the initial bootstrap layer for the migration.
