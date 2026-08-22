# app/tests/unit/test_logging.py
import logging

from app.core.logging import configure_logging


def test_configure_logging_silences_uvicorn_access():
    # N4 regression: uvicorn's own access log records the full request
    # line, including the query string -- unlike RequestIdMiddleware, which
    # only ever logs method/path/status/duration. Nothing accepts a
    # clinical query parameter today, but the first route that does would
    # leak it straight into the log stream unless uvicorn.access is
    # silenced below INFO (the level uvicorn logs access lines at).
    configure_logging()
    assert logging.getLogger("uvicorn.access").getEffectiveLevel() > logging.INFO
