# Kidney Transplant Compatibility System

Full-stack application for kidney transplant compatibility assessment,
donor-recipient risk scoring, and paired kidney exchange matching.

## Services

- **`kidney-backend`** — FastAPI service: auth, patient/donor records, the
  compatibility pipeline (ABO → sensitization → DSA → HLA risk scoring →
  cPRA), paired-exchange matching, audit log.
- **`kidney-frontend`** — React (Vite) UI.
- **`ocr-service`** — FastAPI service that extracts structured data from
  photographed/scanned lab reports via a local vision-LLM. Called by
  `kidney-backend`, not exposed to the frontend directly.
- **`ollama`** — serves the vision-LLM (`qwen3-vl:4b-nothink`) `ocr-service`
  calls out to.
- **`postgres`** — the application database.

Each service's own README has more detail:
[kidney-backend/README.md](kidney-backend/README.md),
[ocr-service/README.md](ocr-service/README.md),
[kidney-frontend/README.md](kidney-frontend/README.md).

## Running the full stack (Docker)

This is the tested, reproducible path — a fresh clone, Docker, and the
steps below is all it takes. Requires Docker with Compose v2 and, for the
first run, enough free disk space and RAM to pull and load a ~3.3GB model
(see "First run: the OCR/model pull" below).

### 1. Configure environment

```bash
cp .env.example .env
```

Fill in every value in `.env`:
- `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` — any values; this
  is a fresh container-managed database.
- `SECRET_KEY` — generate with `openssl rand -hex 32`.
- `OCR_SERVICE_API_KEY` — any value; generate with `openssl rand -hex 32`.
  Shared between `kidney-backend` and `ocr-service` (both read the same
  variable).
- `CORS_ORIGINS` — where the frontend will be browsed from. For the default
  port mapping below, `http://localhost:3000`.
- `VITE_API_BASE_URL` — where the browser reaches the backend. For the
  default port mapping, `http://localhost:8000`.

### 2. Build and start everything

```bash
docker compose -f docker-compose.prod.yml up -d --build
```

`postgres`, `kidney-backend`, and `kidney-frontend` come up within about a
minute — `kidney-backend`'s container runs database migrations
automatically on start, so there's no separate migration step. `ollama` and
`ocr-service` come up independently and are not required for the rest of
the app; see below.

### 3. Create the first account

There's no self-service registration — account creation is an operator
action, run inside the backend container:

```bash
docker compose -f docker-compose.prod.yml exec kidney-backend \
  uv run python -m app.scripts.create_doctor <email> <password> "<full name>"
```

To make that account an admin:

```bash
docker compose -f docker-compose.prod.yml exec kidney-backend \
  uv run python -m app.scripts.promote_admin <email>
```

### 4. Verify it's up

- `GET http://localhost:8000/health` → `{"status":"ok"}`
- `GET http://localhost:8000/health/db` → `{"status":"ok","result":1}` —
  confirms the backend can reach Postgres.
- `http://localhost:3000` — the app itself. Log in with the account from
  step 3.
- `http://localhost:8000/docs` — Swagger UI listing every backend route.

### First run: the OCR/model pull

`ollama` pulls a ~3.3GB model and builds a Modelfile variant of it on its
very first start (see `ocr-service/docker/ollama-entrypoint.sh`) — this can
take up to about an hour depending on network conditions, and `ocr-service`
won't report healthy until it's done. This only happens once per machine;
the model persists in a named volume, so a normal restart is healthy within
seconds. Everything except the photo-upload/OCR-extract step in the
patient/donor intake wizard works fine while this is in progress — watch
progress with:

```bash
docker compose -f docker-compose.prod.yml logs -f ollama
```

This deployment is CPU-only by design (see `ocr-service/README.md`); a GPU
is not required, but extraction is slower without one.

### Stopping / resetting

```bash
docker compose -f docker-compose.prod.yml down          # stop, keep data
docker compose -f docker-compose.prod.yml down -v        # stop and wipe volumes
```

## Local (non-Docker) development

For iterating on one service directly instead of through Docker, see that
service's own README:
[kidney-backend/README.md](kidney-backend/README.md) and
[ocr-service/README.md](ocr-service/README.md) cover their own `.env`
setup, running Postgres/Ollama standalone, and running tests.
[kidney-frontend/README.md](kidney-frontend/README.md) covers `npm run dev`.

## Tech stack

- **Backend**: FastAPI, SQLAlchemy (async), Alembic, PostgreSQL
- **Frontend**: React, Vite, React Router, Tailwind CSS
- **OCR**: FastAPI + Ollama (`qwen3-vl:4b-nothink` vision-LLM)
