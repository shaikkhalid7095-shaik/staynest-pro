from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings

engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    # each query sees the latest committed data. Needed so that after waiting
    # for a row lock, the booking check sees the booking that was just saved.
    isolation_level="READ COMMITTED",
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
