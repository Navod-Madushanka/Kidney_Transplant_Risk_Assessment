FROM ghcr.io/astral-sh/uv:python3.11-bookworm-slim

# Set the working directory inside the container
WORKDIR /app

# Enable bytecode compilation and copy lock/project files
ENV UV_COMPILE_BYTECODE=1
COPY pyproject.toml uv.lock ./

# Install the project's dependencies using uv
RUN uv sync --frozen --no-install-project

# Copy the rest of the application code
COPY . /app

# Install the project itself
RUN uv sync --frozen

# Expose the port FastAPI runs on
EXPOSE 8000

# Run the FastAPI application using uvicorn
# RIGHT
CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]