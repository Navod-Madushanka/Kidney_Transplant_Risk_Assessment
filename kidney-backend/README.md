# Kidney Transplant Compatibility System — Backend

FastAPI service handling auth, patient/donor records, and the kidney
compatibility check pipeline (ABO → sensitization → DSA → HLA risk scoring →
cPRA). This is one of three services in the project — the other two are
`kidney-frontend` (React/Vite) and `ocr-service` (a separate FastAPI service
this backend calls out to for document extraction, backed by a local
vision-LLM via Ollama — not PaddleOCR, which it migrated off of 2026-08-01).

## What's here

```
kidney-backend/
├── app/
│   ├── main.py                 # FastAPI app, router registration, /health endpoints
│   ├── core/
│   │   ├── config.py            # Settings, loaded from .env
│   │   ├── security.py          # Password hashing, JWT create/decode
│   │   └── dependencies.py      # get_current_user and friends
│   ├── db/
│   │   ├── base.py              # Declarative Base
│   │   └── session.py           # Async engine + get_db() dependency
│   ├── models/                  # SQLAlchemy models (doctor, hospital, patient,
│   │                             # donor, HLA typing, antibody profile,
│   │                             # sensitization events, match reports, audit log)
│   ├── schemas/                 # Pydantic request/response models
│   ├── api/                     # Route modules: auth, patients, donors,
│   │                             # compatibility, dashboard, ocr
│   ├── services/                # Business logic: ABO/DSA/HLA-scoring/cPRA/
│   │                             # sensitization services, the match pipeline
│   │                             # that chains them, ocr_client (calls
│   │                             # ocr-service), dashboard/audit services
│   ├── reference_data/           # Static clinical reference tables (ABO
│   │                             # compatibility, HLA loci, mismatch buckets,
│   │                             # risk tiers) sourced from the project's
│   │                             # clinical spec
│   └── tests/unit/               # pytest unit tests for the scoring services
├── alembic/versions/              # Migrations (initial schema → hospitals/doctors
│                                   # → patients/donors → audit logs → NIC numbers)
├── docs/
│   └── clinical-basis.md          # Where every scoring constant in reference_data/
│                                   # actually came from, and what is/isn't externally
│                                   # citable about it
├── alembic.ini
├── pyproject.toml
└── .env.example
```

## What's implemented

- **Auth**: hospital-scoped doctor accounts, register/login, JWT bearer tokens
  (`app/api/auth.py`, `app/core/security.py`).
- **Patients & donors**: CRUD, plus per-patient/donor HLA typing, antibody
  profiles, and sensitization events (`app/api/patients.py`,
  `app/api/donors.py`).
- **Compatibility pipeline** (`app/services/match_pipeline.py`): runs ABO
  compatibility first (halts immediately on failure), then sensitization
  scoring, then a donor-specific-antibody (DSA) check (halts if triggered),
  then HLA mismatch risk scoring and risk-tier classification, then cPRA.
  Every run is persisted as a `MatchReport` and logged to `audit_logs`.
- **Dashboard**: patients with their latest report status, and recent reports
  across a doctor's patients, for the frontend dashboard.
- **OCR integration**: `app/api/ocr.py` proxies uploaded lab report images to
  the separate `ocr-service` and returns structured extraction results
  (demographics, HLA typing, MFI/bead-specificity tables, crossmatch).

See `app/tests/unit/` for the scoring-service test suite — it's the best
place to check expected behavior for ABO, DSA, sensitization, HLA scoring,
risk tiering, and cPRA.

## Setup

### 1. Start Postgres

```bash
docker run --name kt-postgres -e POSTGRES_PASSWORD=devpass -p 5432:5432 -d postgres:16
docker exec -it kt-postgres psql -U postgres -c "CREATE DATABASE kidney_transplant_db;"
```

Redis is present in `Settings` (`redis_url`) and mentioned here for
completeness, but nothing in the app reads from it yet — it's reserved for a
future use (caching, rate limiting, etc.), not required to run the service
today. Skip starting a Redis container unless you're working on something
that needs it.

### 2. Configure environment

```bash
cd kidney-backend
cp .env.example .env
```

Generate a real secret key:

```bash
openssl rand -hex 32
```

Set `DATABASE_URL` to match the Postgres container above, and
`OCR_SERVICE_API_KEY` to match whatever `ocr-service` is configured with
(see its own `.env` / `docker-compose.yml`) if you're testing the OCR flow.

### 3. Install dependencies

```bash
uv venv .venv --python 3.12
source .venv/bin/activate          # on Windows: .venv\Scripts\activate
uv pip install -e ".[dev]"
```

### 4. Run migrations

```bash
alembic upgrade head
```

This applies all current migrations (initial schema → hospitals/doctors →
patients/donors → audit logs → NIC numbers).

### 5. Run the server

```bash
uvicorn app.main:app --reload
```

### 6. Run tests

```bash
pytest
```

### 7. Create a doctor account

There is no self-service `/auth/register` endpoint — accounts are
provisioned by an operator directly:

```bash
uv run python -m app.scripts.create_doctor <email> <full_name> [hospital_name]
```

The password is **never** passed on the command line (it would sit in
shell history and be visible to every other user on the host via `ps` for
the life of the process) — the script prompts for it interactively
(no-echo, entered twice) and rejects anything under 12 characters, a
common/breached password, or an obviously guessable pattern (see
`app/scripts/password_policy.py`). `hospital_name` defaults to "Kandy
National Hospital Sri Lanka" if omitted.

New accounts are never admin by default — promote one separately:

```bash
uv run python -m app.scripts.promote_admin <email>
```

## Verifying it's up

1. `GET http://localhost:8000/health` → `{"status": "ok"}` — liveness, no DB
   dependency.
2. `GET http://localhost:8000/health/db` → `{"status": "ok", "result": 1}` —
   confirms the async SQLAlchemy session can reach Postgres.
3. `http://localhost:8000/docs` — Swagger UI listing every route.

## Notes

- All config lives in `core/config.py`'s `Settings` — nothing should read
  `os.environ` directly elsewhere in the app.
- `/ocr/*` routes require `ocr-service` to be running and reachable at
  `OCR_SERVICE_URL` (defaults to `http://localhost:8001`); without it, the
  photo-upload/OCR-extract step in the frontend wizard will fail, but
  everything else (manual entry, the compatibility pipeline itself) works
  fine without it.
- See the project-level development roadmap for what's still outstanding
  (CI, frontend tests, a unified docker-compose across all three services,
  crossmatch persistence, etc.).
