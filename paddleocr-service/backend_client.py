# paddleocr-service/backend_client.py
"""Thin HTTP client for forwarding extracted report data to the backend
server. Configure via environment variables:

  BACKEND_BASE_URL  e.g. "https://api.yourapp.com" (default: http://localhost:8000)
  BACKEND_API_KEY   optional bearer token sent as "Authorization: Bearer <key>"

Update BACKEND_BASE_URL and the endpoint paths passed from app.py to match
your actual backend routes.
"""
import os

import requests

BACKEND_BASE_URL = os.environ.get("BACKEND_BASE_URL", "http://localhost:8000")
BACKEND_API_KEY = os.environ.get("BACKEND_API_KEY")
REQUEST_TIMEOUT_SECONDS = 10


def send_to_backend(path: str, payload: dict) -> dict:
    """POST payload as JSON to {BACKEND_BASE_URL}{path}.

    Raises requests.HTTPError (or a connection error) if the backend can't
    be reached or returns a non-2xx status, so the caller can decide how to
    handle/report the failure.
    """
    headers = {"Content-Type": "application/json"}
    if BACKEND_API_KEY:
        headers["Authorization"] = f"Bearer {BACKEND_API_KEY}"

    response = requests.post(
        f"{BACKEND_BASE_URL}{path}",
        json=payload,
        headers=headers,
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    response.raise_for_status()

    try:
        return response.json()
    except ValueError:
        return {}