# app/tests/unit/test_db_session_config.py
"""Part H fix: app/db/session.py's engine used to be created with
`echo=True` unconditionally and no pool tuning at all (5 + 10 overflow
default, no pool_pre_ping). echo=True already escaped into production
once -- it logs every statement's bound parameters, including the full
`documents` JSONB blob on every one of an OcrExtractionJob's 16+ commits
per job. Cheap to pin down with a direct assertion so it can't silently
regress again.
"""
from app.db.session import engine


def test_echo_is_disabled_by_default():
    assert engine.echo is False


def test_pool_pre_ping_is_enabled():
    # asyncpg connections get killed by the DB or the network without the
    # pool knowing; without this a stale one surfaces as a random mid-job
    # error instead of being transparently replaced.
    assert engine.pool._pre_ping is True


def test_pool_is_sized_and_fails_fast():
    # Values themselves matter less than "someone configured this
    # deliberately" -- see app/db/session.py's own comments for the
    # reasoning behind each number.
    assert engine.pool.size() == 10
    assert engine.pool._max_overflow == 20
    assert engine.pool._timeout == 10
