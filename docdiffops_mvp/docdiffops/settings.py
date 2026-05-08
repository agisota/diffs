from __future__ import annotations

import os
from pathlib import Path

DATA_DIR = Path(os.getenv("DATA_DIR", "./data")).resolve()
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# DATABASE_URL: defaults to the docker-compose Postgres URL. When TESTING=1 is
# set we fall back to an in-memory SQLite engine so unit tests can run without
# a live Postgres. The compose default keeps `docker compose up && alembic
# upgrade head` working out of the box.
TESTING = os.getenv("TESTING") == "1"
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "sqlite:///:memory:" if TESTING
    else "postgresql+psycopg2://docdiff:docdiff@db:5432/docdiff",
)

DATA_DIR.mkdir(parents=True, exist_ok=True)
