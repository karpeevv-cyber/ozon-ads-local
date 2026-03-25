# Deployment

## New stack services

The new migration stack now has a shared Docker Compose entrypoint:

- `postgres`
- `redis`
- `backend`
- `frontend`
- `nginx`

Legacy Streamlit is intentionally not included here and remains the fallback contour.

## Initial setup

1. Create `.env` from `.env.example`
2. Fill in Ozon credentials
3. Start the stack

```bash
docker compose up --build
```

## URLs

- Frontend through nginx: `http://localhost/`
- Backend API through nginx: `http://localhost/api/health`
- Backend direct: `http://localhost:8000/api/health`
- Frontend direct: `http://localhost:3000/`

## Notes

- `DATABASE_URL` points to postgres inside compose
- `API_BASE_URL` is used by server-side Next.js fetches and should point to `http://backend:8000/api` inside compose
- `NEXT_PUBLIC_API_BASE_URL` defaults to `/api`, so browser requests stay behind nginx instead of baking a host-specific URL into the frontend bundle
- the frontend container uses production standalone output, not `next dev`
- `backend_data` persists backend-owned cache and mirror files under `/app/backend/data`
- later we will add production overrides, migrations, and worker services
