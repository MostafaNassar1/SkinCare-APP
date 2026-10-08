from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import get_settings

settings = get_settings()

# One engine for the whole app; it manages a pool of reusable connections
engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,  # test each connection before use, so dropped connections are replaced
)

# Factory that creates a new database session for each request
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
