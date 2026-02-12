"""SQLite connection manager for the LaFrieda ERP testbed."""

from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from config.settings import DB_PATH, DB_URL
from database.models import Base


def _enable_fk_support(dbapi_connection, _connection_record):
    """Enable foreign key enforcement in SQLite."""
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


def get_engine(echo: bool = False):
    """Create and return a SQLAlchemy engine."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(DB_URL, echo=echo)
    event.listen(engine, "connect", _enable_fk_support)
    return engine


def create_tables(engine=None):
    """Create all tables defined in models.py."""
    if engine is None:
        engine = get_engine()
    Base.metadata.create_all(engine)
    return engine


def drop_tables(engine=None):
    """Drop all tables."""
    if engine is None:
        engine = get_engine()
    Base.metadata.drop_all(engine)
    return engine


def get_session(engine=None):
    """Create and return a new database session."""
    if engine is None:
        engine = get_engine()
    Session = sessionmaker(bind=engine)
    return Session()


def reset_database():
    """Drop and recreate all tables."""
    engine = get_engine()
    drop_tables(engine)
    create_tables(engine)
    return engine
