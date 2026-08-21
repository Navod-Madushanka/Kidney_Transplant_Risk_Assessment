FROM python:3.11-slim

# No OpenCV/PaddlePaddle system libraries needed anymore — this service no
# longer runs PaddleOCR in-process. Extraction now calls out to a separate
# Ollama service (see docker-compose.yml) as of the OCR -> local
# vision-LLM migration; see claude/ocr-to-local-llm-migration-plan.md.

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# README.md must be copied before `uv sync` -- pyproject.toml declares it as
# the package readme (readme = "README.md"), and this single `uv sync` step
# both installs deps AND builds+installs the project itself (unlike
# kidney-backend's two-step Dockerfile), so hatchling's metadata validation
# runs here and fails with "Readme file does not exist" without it.
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev

COPY app/ ./app/

EXPOSE 8001

# Part H fix: --reload was shipping in the production image. Combined with
# docker-compose.yml's ./app bind mount, touching ANY file under ./app on
# the host restarted the worker and destroyed every in-flight multi-minute
# extraction. kidney-backend's own Dockerfile never had this -- it was an
# oversight in this one image, not a deliberate convention. --reload (and
# the bind mount that makes it useful for local dev) now lives ONLY in
# docker-compose.override.yml, alongside the other dev-only settings.
CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001"]
