# app/db/session.py
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import get_settings

settings = get_settings()

engine = create_async_engine(settings.database_url, echo=True)
async_session_maker = async_sessionmaker(engine, expire_on_commit=False)

async def get_db():
    async with async_session_maker() as session:
        yield session
