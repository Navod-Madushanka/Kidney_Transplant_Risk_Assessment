# Kidney Transplant Compatibility System — OCR Service

FastAPI service that extracts structured data (demographics, HLA typing,
MFI/bead-specificity tables, crossmatch results) from photographed or
scanned lab report images. Called by `kidney-backend`'s `/ocr/*` routes — it
is not exposed directly to the frontend. Extraction runs on a local
vision-LLM via [Ollama](https://ollama.com) (`qwen3-vl:4b-nothink`), not
PaddleOCR, which this service migrated off of 2026-08-01 — see
`../llm-migration-spike/README.md` for the migration's Phase 1 rationale
and validation results.

## What's here

```
ocr-service/
├── app/
│   ├── main.py            # FastAPI app, /health
│   ├── api/routes.py       # extraction endpoints kidney-backend calls
│   ├── extraction/         # image preprocessing, tiling, bead reconciliation
│   ├── llm/                # Ollama client, prompts, response schemas
│   ├── core/config.py      # Settings, loaded from .env
│   └── reference_data/     # bead-panel reference tables
├── docker/
│   └── ollama-entrypoint.sh   # builds the -nothink model variant on first boot
├── docker-compose.yml          # ocr-service + ollama, CPU-only base
├── docker-compose.override.yml # dev-only: GPU passthrough + --reload (gitignored)
├── Dockerfile
└── pyproject.toml
```

## Running it

**As part of the full stack (recommended):** see the root
[`README.md`](../README.md) — `docker-compose.prod.yml` at the repo root
brings this service up together with `ollama`, `kidney-backend`,
`kidney-frontend`, and `postgres`.

**Standalone, for OCR-focused dev work:**

```bash
cd ocr-service
cp .env.example .env   # if you don't already have a .env — see below
docker compose up -d --build
```

This starts just `ocr-service` + `ollama` (`docker-compose.yml`). On a dev
machine with an NVIDIA GPU, `docker-compose.override.yml` is picked up
automatically alongside it and adds GPU passthrough plus `--reload` +
a live-editing bind mount — see that file's own comments for why it's kept
separate from the base file and never meant to reach prod.

First boot pulls the ~3.3GB base model and builds the `-nothink` Modelfile
variant (`docker/ollama-entrypoint.sh`) — this can take up to about an hour
depending on network conditions, and is why the `ollama` healthcheck in
`docker-compose.yml` has a generous retry budget. It only happens once per
machine; the model persists in the `ollama-models` volume after that, so a
normal restart reports healthy within seconds. Watch progress with:

```bash
docker compose logs -f ollama
```

`.env` needs (see `docker-compose.yml`'s `environment:` block for how these
map into the container — there is no `.env.example` checked in here since
`OCR_SERVICE_API_KEY` is the only value a fresh clone actually needs):

- `OCR_SERVICE_API_KEY` — must match whatever `kidney-backend` is
  configured with for the same variable.
- `OLLAMA_BASE_URL` — defaults to `http://localhost:11434` for running this
  service directly on the host against a native `ollama serve`;
  `docker-compose.yml` overrides it to `http://ollama:11434` for the
  containerized service.

## Verifying it's up

`GET http://localhost:8001/health` → `{"status": "ok", "service": "ocr-service"}`
— liveness only, doesn't confirm Ollama is reachable. A real extraction call
will fail with a clear error if Ollama/the model isn't ready yet; check
`docker compose logs ollama` in that case.

## Memory limits

Both containers in `docker-compose.yml` set `mem_limit`, for different
reasons — see the inline comments there for the numbers:

- `ocr-service`: bounds PIL decode + tiling peak (image processing), not
  the model.
- `ollama`: bounds the model itself — weights + KV cache + compute
  buffers.

`docker-compose.prod.yml` at the repo root carries the same `ollama`
`mem_limit` forward for the full-stack deployment.

## Notes

- All config lives in `app/core/config.py`'s `Settings` — nothing should
  read `os.environ` directly elsewhere in the app.
- This base `docker-compose.yml` is already CPU-only / prod-shaped on
  purpose (no GPU block) — GPU passthrough is dev-machine-only and lives
  entirely in `docker-compose.override.yml`, which is gitignored and never
  meant to travel to a deployment target.
