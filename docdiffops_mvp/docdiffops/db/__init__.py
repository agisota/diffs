"""Database layer: engine, session factory, and ORM models.

PR-1.1 only introduces the schema. Reads/writes from the rest of the
codebase land in PR-1.2 (dual-write) and PR-1.3 (cutover).
"""
from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from docdiffops.settings import DATABASE_URL

# SQLite needs a special connect arg for cross-thread use; everything else
# (psycopg2 against Postgres) takes default arguments.
_connect_args: dict = {}
if DATABASE_URL.startswith("sqlite"):
    _connect_args["check_same_thread"] = False

engine: Engine = create_engine(
    DATABASE_URL,
    future=True,
    pool_pre_ping=True,
    connect_args=_connect_args,
)

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
    future=True,
)


@contextmanager
def get_session() -> Iterator[Session]:
    """Yield a session and commit on success / rollback on error."""
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


__all__ = ["engine", "SessionLocal", "get_session"]
