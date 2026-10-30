"""Keeps tests away from the real database. Fixtures here TRUNCATE `mem.*` and
`eval.*`, so this must run before anything reads the settings: a conftest at the
root is imported first, and the environment wins over `.env`."""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import psycopg
import pytest
from dotenv import dotenv_values
from psycopg import sql

_TEST_DB = os.environ.get("AGX_TEST_DB_NAME", "agenticenv_test")
if not _TEST_DB.endswith("_test"):
    raise RuntimeError(f"refusing to run tests on {_TEST_DB!r}: the name must end in _test")
os.environ["AGX_DB_NAME"] = _TEST_DB

_ENV = {**dotenv_values(Path(__file__).parent / ".env"), **os.environ}


def _admin_connection(database: str) -> psycopg.Connection:
    return psycopg.connect(
        host=_ENV.get("AGX_DB_HOST", "127.0.0.1"),
        port=int(_ENV.get("AGX_DB_PORT") or 5432),
        user=_ENV["AGX_DB_ADMIN_USER"],
        password=_ENV["AGX_DB_ADMIN_PASSWORD"],
        dbname=database,
        autocommit=True,
    )


@pytest.fixture(scope="session", autouse=True)
def _fresh_test_database(request: pytest.FixtureRequest) -> Iterator[None]:
    """A database rebuilt for each run, only when a selected test needs one."""
    if not any(item.get_closest_marker("integration") for item in request.session.items):
        yield
        return

    name = sql.Identifier(_TEST_DB)
    role = sql.Identifier(_ENV["AGX_DB_USER"])
    with _admin_connection("postgres") as admin:
        admin.execute(sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(name))
        admin.execute(sql.SQL("CREATE DATABASE {}").format(name))
    with _admin_connection(_TEST_DB) as admin:
        for extension in ("vector", "pg_trgm", "unaccent"):
            admin.execute(
                sql.SQL("CREATE EXTENSION IF NOT EXISTS {}").format(sql.Identifier(extension))
            )
        admin.execute(sql.SQL("GRANT ALL PRIVILEGES ON DATABASE {} TO {}").format(name, role))
        admin.execute(sql.SQL("GRANT CREATE ON SCHEMA public TO {}").format(role))
    yield
