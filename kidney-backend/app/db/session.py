# app/db/session.py
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import get_settings

settings = get_settings()

engine = create_async_engine(
    settings.database_url,
    echo=settings.sql_echo,
    # Part H fix: ocr_job_service.run_extraction_job used to hold one of
    # these connections checked out for the full 1.5-3 minutes of an
    # extraction call (a session opened before the OCR await and closed
    # after it), which exhausted the old unconfigured pool (default 5 +
    # 10 overflow) at roughly 15 concurrent jobs and 503'd every other
    # request, including the polling GETs and /health/db. That's fixed by
    # never holding a session across an await on ocr-service (see
    # run_extraction_job's docstring) -- these numbers are a modest bump
    # on top of that fix, not a substitute for it. Raising pool_size alone
    # without that fix just moves the wall; the ratio of held-to-useful
    # connection time is what matters.
    pool_size=10,
    max_overflow=20,
    # Fail fast rather than the 30s default -- a quick 503 the frontend can
    # show and retry is better than every request silently stalling for
    # half a minute under pressure.
    pool_timeout=10,
    # asyncpg connections get killed by the DB or the network without the
    # pool knowing; without this a stale one surfaces as a random mid-job
    # error instead of being transparently replaced.
    pool_pre_ping=True,
)
async_session_maker = async_sessionmaker(engine, expire_on_commit=False)

async def get_db():
    async with async_session_maker() as session:
        yield session
