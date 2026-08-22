# app/core/logging.py
"""
Structured JSON logging (B15 / Phase 3.6 of FINALIZATION-PLAN.md).

Every log line this process emits is one JSON object on stdout --
timestamp, level, logger name, message, request_id (see
app/core/request_logging.py's RequestIdMiddleware), plus whatever
`extra={...}` a caller passes. This is an *operational* log for diagnosing
a failed OCR extraction or a 500 in the pilot, not the clinical audit trail
-- see app/services/audit_service.py for that (tamper-evident, hash-chained,
answers "who did what to which patient").

HARD RULE, no exceptions: never pass a patient/donor name, NIC, HLA
antigen, or MFI value into a log call, here or anywhere else in this app.
If you need to log an identifier for debugging, log the UUID primary key,
never a name or NIC -- a UUID on its own doesn't identify a real person to
anyone reading the log file. request/response bodies are deliberately
never logged (RequestIdMiddleware logs method, path, status, and duration
only, never the body or query string) specifically so a route that happens
to accept or return clinical data can't leak it into the log stream just by
being called.
"""
import contextvars
import json
import logging
import sys
from typing import Any

# Set by RequestIdMiddleware for the lifetime of one request; read here so
# every log line emitted while handling that request carries the same
# request_id without every call site having to thread it through
# explicitly. "-" outside any request (startup/shutdown/background sweeps).
_request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar(
    "request_id", default="-"
)


def get_request_id() -> str:
    return _request_id_var.get()


def set_request_id(request_id: str) -> contextvars.Token:
    return _request_id_var.set(request_id)


def reset_request_id(token: contextvars.Token) -> None:
    _request_id_var.reset(token)


# Every attribute a bare logging.LogRecord carries -- used to separate a
# caller's `extra={...}` keys (which should appear in the JSON payload)
# from the record's own bookkeeping attributes (which shouldn't be
# duplicated). Computed once from a throwaway record rather than
# hand-maintained, so it can't silently drift from whatever this Python
# version's LogRecord actually carries.
_RESERVED_RECORD_ATTRS = set(logging.LogRecord("", 0, "", 0, "", (), None).__dict__) | {
    "message",
    "asctime",
}


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": _request_id_var.get(),
        }
        for key, value in record.__dict__.items():
            if key not in _RESERVED_RECORD_ATTRS:
                payload[key] = value
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        # default=str: a caller's extra={} can legitimately include a UUID,
        # Decimal, or datetime -- none of those are JSON-serializable on
        # their own, and a logging call should never raise for that reason.
        return json.dumps(payload, default=str)


def configure_logging(level: str = "INFO") -> None:
    """Call once, at process startup, before anything logs. Replaces the
    root handler with a single JSON-formatted stdout stream and routes
    uvicorn's own loggers through it too, so every line this process
    produces -- app code and uvicorn's access/error logs alike -- is the
    same shape rather than app code logging JSON next to uvicorn's default
    plain-text lines.
    """
    root = logging.getLogger()
    root.setLevel(level)
    root.handlers.clear()

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(_JsonFormatter())
    root.addHandler(handler)

    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        uv_logger = logging.getLogger(name)
        uv_logger.handlers.clear()
        uv_logger.propagate = True


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
