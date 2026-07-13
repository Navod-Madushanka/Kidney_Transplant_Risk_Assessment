FROM python:3.11-slim

# System libraries required by OpenCV/PaddleOCR that aren't in the slim image:
# - libgl1: OpenGL support, needed by OpenCV's image handling
# - libglib2.0-0: core low-level library OpenCV depends on
# - libgomp1: OpenMP runtime, used for PaddlePaddle's parallel computation
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY app/ ./app/

EXPOSE 8001

CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001", "--reload"]