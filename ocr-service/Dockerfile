FROM python:3.11-slim

# No OpenCV/PaddlePaddle system libraries needed anymore — this service no
# longer runs PaddleOCR in-process. Extraction now calls out to a separate
# Ollama service (see docker-compose.yml) as of the OCR -> local
# vision-LLM migration; see claude/ocr-to-local-llm-migration-plan.md.

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY app/ ./app/

EXPOSE 8001

CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001", "--reload"]
