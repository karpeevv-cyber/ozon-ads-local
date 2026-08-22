# Codex Project Handoff: Marketrix / Ozon Ads

Read this file before doing any work in this repository. It contains the standing operating rules and production context for this project.

## User Working Agreement

- Communicate with the user in Russian unless asked otherwise.
- For requested code changes, continue through implementation, verification, commit, push, and production deployment in the same task.
- Always commit and push completed changes immediately. Do not wait for a separate request.
- Deploy completed changes to production and verify the affected service after deployment.
- Do not revert unrelated user changes in a dirty worktree.
- Ignore the local untracked paths `.playwright-mcp/` and `tmp_openclaw_bash_profile` unless the user explicitly asks about them.
- Use `apply_patch` for manual file edits.
- Prefer `rg` / `rg --files` for repository search.
- Never commit credentials, Telegram tokens, Ozon keys, passwords, `.env`, SSH private keys, database dumps, or production user data.

## Repository And Production

- GitHub repository: `https://github.com/karpeevv-cyber/ozon-ads-local.git`
- Main branch: `main`
- Local Windows workspace normally used: `C:\Users\User\ozon-ads-local`
- Production domain: `https://marketrix.ru/`
- Production server: `82.38.66.248`
- SSH user and port: `root`, port `22`
- SSH command: `ssh root@82.38.66.248`
- Production repository path: `/opt/ozon-ads-local`
- Production timezone for application logic: `Europe/Moscow`
- Server OS clock may display another timezone; application schedules use `TZ=Europe/Moscow`.

The server also hosts VPN software. Do not change firewall, routing, ports `80/443`, nginx ownership, VPN/Xray/Amnezia configuration, or reboot the server unless the user explicitly requests it and the impact has been checked.

## Architecture

The active service is:

- `backend/`: FastAPI backend.
- `frontend/`: Next.js frontend.
- PostgreSQL: durable application state.
- Redis: cache/supporting runtime.
- nginx: public reverse proxy and TLS termination.
- Docker Compose: production process manager.

The repository also contains a legacy Streamlit implementation used as a reference/fallback. Read `PROJECT_GUIDE.md` for the boundary between active and legacy code. For a new task, use this reading order:

1. `AGENTS.md`
2. `PROJECT_GUIDE.md`
3. Relevant feature code under `backend/app/services`, `backend/app/api`, and `frontend/src/features`
4. `docs/RUNBOOK.md` and `docs/STATUS.md` when operational or migration context is needed

Prefer PostgreSQL/backend-managed state for new persistent features. Do not add new CSV/PKL persistence unless compatibility with legacy code makes it unavoidable.

## Production Services And Ports

- Public frontend: `https://marketrix.ru/`
- Public API health: `https://marketrix.ru/api/health`
- Backend direct on server: `http://127.0.0.1:8000/api`
- Frontend direct on server: `http://127.0.0.1:3000`
- PostgreSQL Compose service: `postgres`, port `5432`
- Redis Compose service: `redis`, port `6379`
- Compose services: `postgres`, `redis`, `backend`, `frontend`, `nginx`

## Standard Git And Deployment Flow

Before editing:

```powershell
git status --short
git log -5 --oneline
```

Run focused tests plus the relevant broad checks. Typical checks:

```powershell
.\.venv\Scripts\python.exe -m py_compile <changed-python-files>
git diff --check
```

For frontend changes:

```powershell
Set-Location frontend
npm.cmd run build
```

The current `npm run lint` command may launch an interactive Next.js ESLint setup if ESLint has not been configured. Do not treat that prompt as a successful lint run and do not configure lint incidentally unless it is part of the task.

Commit only task-related files, then push:

```powershell
git add <explicit-task-files>
git commit -m "Concise imperative message"
git push origin main
```

Deploy backend and frontend changes:

```powershell
ssh root@82.38.66.248 "cd /opt/ozon-ads-local && git pull --ff-only && docker compose up -d --build backend frontend"
```

For backend-only changes, rebuild only backend. For frontend-only changes, rebuild only frontend. Rebuild both if API contracts shared by frontend/backend changed.

Verify deployment:

```powershell
ssh root@82.38.66.248 "curl -fsS --max-time 20 http://127.0.0.1:8000/api/health; cd /opt/ozon-ads-local && docker compose ps && docker compose logs --since=3m backend frontend | grep -E 'ERROR|Traceback|Exception|Failed' || true"
```

For a page check:

```powershell
ssh root@82.38.66.248 "curl -I -s --max-time 20 'https://marketrix.ru/?tab=main' | head -n 8"
```

Do not run `docker compose down -v`, delete volumes, reset PostgreSQL, replace `.env`, or use destructive Git commands.

## Credentials And Secret Locations

No secret values belong in this file or repository.

- Production runtime secrets are already stored in `/opt/ozon-ads-local/.env` and in the production database organization/credential records.
- `.env` is Git-ignored. Use `.env.example` only as the list of expected variables.
- Important variable names include `PERF_CLIENT_ID`, `PERF_CLIENT_SECRET`, `SELLER_CLIENT_ID`, `SELLER_API_KEY`, `TG_BOT_TOKEN`, company-specific Telegram chat IDs, `SECRET_KEY`, `DATABASE_URL`, `REDIS_URL`, and `TZ`.
- Companies currently used by the application include `aura` and `osome`.
- Never print complete secrets in terminal output or chat. Mask values when diagnosing configuration.
- Do not overwrite production `.env` from a local file. Edit only the specific variable requested and preserve the rest.

## Scheduled Jobs And Important Current Behavior

- Finance Telegram summary runs daily at `08:00` application timezone.
- Auto-bid strategy runs daily at `08:00` application timezone and analyzes the previous calendar day.
- Ozon Seller Analytics can finalize previous-day revenue after `08:00`; a zero in the early Telegram finance summary may be stale even when a later query returns revenue.
- Auto-bid rules currently are:
  - spend `< 50 RUB`: increase bid by 20%, capped by the campaign/SKU maximum;
  - spend `50..150 RUB`: no change;
  - spend `> 150 RUB` with no total SKU sales: decrease by 10%;
  - spend `> 150 RUB` with DRR above 25%: decrease by 10%;
  - spend `> 150 RUB` with sales and DRR at or below 25%: no change.
- Per-campaign/SKU maximum bids are stored in PostgreSQL and editable in `All campaigns` under `max bid`. The company fallback maximum is `25 RUB` when no individual limit exists.
- Telegram auto-bid messages are grouped into increased bids, decreased bids, manual review, and errors.
- As of August 2026, Ozon Performance API credentials for `osome` have returned HTTP `403` on campaign-list requests. Re-check this before assuming an application regression. Seller API data for `osome` may still work independently.

## Domain Safety Rules

- Revenue used in campaign DRR and auto-bid decisions is total Seller Analytics SKU revenue, not only ad-attributed orders.
- Treat Ozon Analytics, Finance, Stocks, Supply, and Performance endpoints as distinct data sources with different update delays.
- For shipment work, preserve unmapped destinations as `UNKNOWN` rather than silently dropping them.
- Stocks and shipment caches are production state. Verify cache timestamps and timezone before diagnosing stale data.
- Avoid fallback calculations that invent shipment completion dates or merge bundle dates with individual supply dates.
- Mutating UI/API routes should require authentication. Reads may follow the existing feature's access pattern.

## New Laptop Bootstrap

This repository file transfers project knowledge but intentionally does not contain access keys. Complete these steps once on the new Windows laptop:

1. Install Git, Docker Desktop if local containers are needed, Node.js, Python, and Codex.
2. Securely transfer the SSH private key from the old laptop to the same path under `%USERPROFILE%\.ssh`. Use an encrypted removable drive, password manager secure file storage, or another end-to-end encrypted channel. Never upload the key to Codex or commit it.
3. Ensure the key file is readable only by the Windows user where practical.
4. Verify production access:

```powershell
ssh root@82.38.66.248 "hostname && cd /opt/ozon-ads-local && git status --short"
```

5. Clone the repository:

```powershell
git clone https://github.com/karpeevv-cyber/ozon-ads-local.git
Set-Location ozon-ads-local
```

6. Open the cloned repository folder in Codex. Codex should read this `AGENTS.md` automatically.
7. Configure GitHub authentication on the new laptop so `git push origin main` succeeds. Use Git Credential Manager or `gh auth login`; do not place a GitHub token in this file.

If only this file is uploaded to a new Codex task before cloning, instruct Codex: `Read the attached AGENTS.md, clone the repository, verify SSH access, then continue with my task.`

