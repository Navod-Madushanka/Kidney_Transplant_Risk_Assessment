# Backend — Phase 1: Skeleton

Proves FastAPI can run and can actually talk to Postgres, before any real
domain models exist.

## What's in this phase

```
backend/
├── app/
│   ├── main.py            # FastAPI app + /health and /health/db endpoints
│   ├── core/
│   │   └── config.py       # Settings, loaded from .env
│   └── db/
│       ├── base.py         # Empty declarative Base (models added in Phase 4)
│       └── session.py      # Async engine + get_db() dependency
├── alembic/
│   ├── env.py               # Wired to use app.core.config.Settings
│   ├── script.py.mako
│   └── versions/            # Empty for now — first migration comes in Phase 4
├── alembic.ini
├── pyproject.toml
├── .env.example
└── .gitignore
```

## Setup (run these on your own machine — this was scaffolded in a sandbox without network/Docker access, so it hasn't been executed yet)

### 1. Start Postgres and Redis

```bash
docker run --name kt-postgres -e POSTGRES_PASSWORD=devpass -p 5432:5432 -d postgres:16
docker run --name kt-redis -p 6379:6379 -d redis:7
```

Create the actual database (the container starts with a default `postgres` db, but we want our own):

```bash
docker exec -it kt-postgres psql -U postgres -c "CREATE DATABASE kidney_transplant_db;"
```

### 2. Configure environment

```bash
cd backend
cp .env.example .env
```

Generate a real secret key and put it in `.env`:

```bash
openssl rand -hex 32
```

The default `DATABASE_URL` in `.env.example` already matches the Docker command above, so if you used those exact values you don't need to change it.

### 3. Install dependencies

```bash
uv venv .venv --python 3.12
source .venv/bin/activate          # on Windows: .venv\Scripts\activate
uv pip install -e ".[dev]"
```

### 4. Run the server

```bash
uvicorn app.main:app --reload
```

## Verification checklist (Phase 1 is done when all of these are true)

1. **`GET http://localhost:8000/health`** returns:
   ```json
   {"status": "ok"}
   ```
   This proves FastAPI itself is running, independent of the database.

2. **`GET http://localhost:8000/health/db`** returns:
   ```json
   {"status": "ok", "database": "connected", "result": 1}
   ```
   This proves FastAPI can execute a real query against Postgres through
   the async SQLAlchemy session. If you get `{"status": "error", ...}`
   instead, check in this order:
   - Is the Postgres container actually running? `docker ps`
   - Does `DATABASE_URL` in `.env` match the container's credentials/port?
   - Does the `kidney_transplant_db` database exist? (Step 1 above creates it.)

3. **`http://localhost:8000/docs`** loads the Swagger UI and shows both
   endpoints listed.

4. **Alembic is wired correctly** (no migrations exist yet — this just
   confirms the plumbing works ahead of Phase 4):
   ```bash
   alembic current
   ```
   Should run without error and print nothing (no migrations applied yet),
   rather than throwing a connection or import error.

## Why things are structured this way

- **Settings in one place (`core/config.py`)**: every later phase that needs
  config (JWT secret, Redis URL, etc.) reads from this same `Settings` object.
  Nothing should ever call `os.environ.get(...)` directly elsewhere in the app.
- **`/health` vs `/health/db` are separate**: a load balancer or orchestrator
  doing liveness checks should hit `/health` (cheap, no DB dependency). Only
  hit `/health/db` for deeper readiness checks, since it adds DB load on
  every call.
- **`app/db/base.py` exists now, empty**: so that Alembic's `env.py` never
  needs to be touched again once real models are added in Phase 4 — the
  import target is already correct.
- **Alembic reads the URL from `Settings`, not from `alembic.ini` directly**:
  one source of truth for the connection string. Editing `.env` is enough;
  you never need to remember to also update `alembic.ini`.

## Next: Phase 2

Once all four verification steps above pass, move to the frontend skeleton
(React + Tailwind hitting `/health/db` and showing "Backend connected").
