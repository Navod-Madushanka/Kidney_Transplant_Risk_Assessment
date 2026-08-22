# app/tests/unit/test_audit_service.py
"""Pure-function tests for compute_audit_hash. The chain-building and
verify_audit_chain behavior (which needs real committed rows to hash and
tamper with) lives in app/tests/integration/test_audit_service.py."""
import uuid
from datetime import datetime, timezone

from app.services.audit_service import GENESIS_HASH, compute_audit_hash


def test_compute_audit_hash_is_deterministic():
    created_at = datetime(2026, 8, 8, 12, 0, 0, tzinfo=timezone.utc)
    doctor_id = uuid.uuid4()
    row_id = uuid.uuid4()

    first = compute_audit_hash(
        GENESIS_HASH, doctor_id, None, None, "did_a_thing", created_at, {"a": 1, "b": 2}, row_id
    )
    second = compute_audit_hash(
        GENESIS_HASH, doctor_id, None, None, "did_a_thing", created_at, {"b": 2, "a": 1}, row_id
    )

    # dict key insertion order shouldn't change the hash -- callers build
    # `details` fresh every call, so order carries no meaning.
    assert first == second
    assert len(first) == 64


def test_compute_audit_hash_changes_with_any_hashed_field():
    created_at = datetime(2026, 8, 8, 12, 0, 0, tzinfo=timezone.utc)
    doctor_id = uuid.uuid4()
    row_id = uuid.uuid4()
    base = compute_audit_hash(
        GENESIS_HASH, doctor_id, None, None, "action", created_at, {"k": "v"}, row_id
    )

    assert (
        compute_audit_hash(
            "f" * 64, doctor_id, None, None, "action", created_at, {"k": "v"}, row_id
        )
        != base
    )
    assert (
        compute_audit_hash(
            GENESIS_HASH, uuid.uuid4(), None, None, "action", created_at, {"k": "v"}, row_id
        )
        != base
    )
    assert (
        compute_audit_hash(
            GENESIS_HASH, doctor_id, None, None, "other_action", created_at, {"k": "v"}, row_id
        )
        != base
    )
    assert (
        compute_audit_hash(
            GENESIS_HASH, doctor_id, None, None, "action", created_at, {"k": "other"}, row_id
        )
        != base
    )
    assert (
        compute_audit_hash(
            GENESIS_HASH, doctor_id, uuid.uuid4(), None, "action", created_at, {"k": "v"}, row_id
        )
        != base
    )
    # Review #2 bug 16: the row's own id is now part of the digest, so
    # rewriting it (with every other field held equal) must also change
    # the hash -- previously it wouldn't have.
    assert (
        compute_audit_hash(
            GENESIS_HASH, doctor_id, None, None, "action", created_at, {"k": "v"}, uuid.uuid4()
        )
        != base
    )
