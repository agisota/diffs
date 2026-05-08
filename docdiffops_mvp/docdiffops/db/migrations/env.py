"""Alembic env.py — wires the docdiffops models into autogenerate.

Reads DATABASE_URL from the environment at runtime (with the same default
as docdiffops.settings: the docker-compose Postgres URL). Tests can point
this at SQLite via TESTING=1 or by exporting DATABASE_URL.
"""
from __future__ import annotations

import os
import sys
from logging.config import fileConfig
from pathlib import Path

from sqlalchemy import engine_from_config, pool

from alembic import context

# Make the docdiffops package importable when alembic is invoked from
# anywhere (project root, container, test).
_HERE = Path(__file__).resolve()
_PACKAGE_ROOT = _HERE.parents[3]  # docdiffops_mvp/
if str(_PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(_PACKAGE_ROOT))

from docdiffops.db.models import Base  # noqa: E402

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Pull DATABASE_URL from env at runtime; honor TESTING=1 the same way settings.py does.
_TESTING = os.getenv("TESTING") == "1"
_DEFAULT_URL = (
    "sqlite:///:memory:" if _TESTING
    else "postgresql+psycopg2://docdiff:docdiff@db:5432/docdiff"
)
_DATABASE_URL = os.getenv("DATABASE_URL", _DEFAULT_URL)
config.set_main_option("sqlalchemy.url", _DATABASE_URL)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=connection.dialect.name == "sqlite",
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
