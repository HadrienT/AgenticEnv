from __future__ import annotations

import re
import threading
from collections.abc import Iterator
from contextlib import contextmanager

from pydantic import BaseModel
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from corelib.config import get_settings
from corelib.logging import get_logger

logger = get_logger(__name__)

_MIGRATION_NAME_RE = re.compile(r"^(\d{4})_[a-z0-9_]+\.sql$")

_engine_lock = threading.Lock()
_engine: Engine | None = None
_session_factory: sessionmaker[Session] | None = None


class HealthStatus(BaseModel):
    ok: bool
    migration_version: str | None
    detail: str


class MigrationReport(BaseModel):
    applied: list[str]
    already_up_to_date: bool


def get_engine() -> Engine:
    """Lazily built, process-wide SQLAlchemy engine, bound to `settings.database`."""
    global _engine, _session_factory
    if _engine is not None:
        return _engine
    with _engine_lock:
        if _engine is None:
            db = get_settings().database
            url = (
                f"postgresql+psycopg://{db.user}:{db.password.get_secret_value()}"
                f"@{db.host}:{db.port}/{db.database}"
            )
            engine = create_engine(
                url,
                connect_args={"options": f"-c statement_timeout={db.statement_timeout_ms}"},
                pool_pre_ping=True,
            )
            _session_factory = sessionmaker(bind=engine, expire_on_commit=False)
            _engine = engine
    return _engine


def _get_session_factory() -> sessionmaker[Session]:
    get_engine()
    assert _session_factory is not None  # set alongside _engine under the same lock
    return _session_factory


@contextmanager
def session_scope() -> Iterator[Session]:
    """Commits on normal exit, rolls back on exception, always closes."""
    session = _get_session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def check_health() -> HealthStatus:
    """`SELECT 1` + latest applied migration version. Never raises: reports `ok=False`."""
    try:
        with session_scope() as session:
            session.execute(text("SELECT 1"))
            row = session.execute(
                text(
                    "SELECT version FROM public.schema_migrations ORDER BY applied_at DESC LIMIT 1"
                )
            ).first()
        version = row[0] if row else None
        return HealthStatus(ok=True, migration_version=version, detail="SELECT 1 succeeded")
    except Exception as exc:
        logger.warning("db health check failed", extra={"error": str(exc)})
        return HealthStatus(ok=False, migration_version=None, detail=str(exc))


def apply_migrations(target: str | None = None) -> MigrationReport:
    """Applies `migrations/NNNN_*.sql` in order; idempotent via `public.schema_migrations`."""
    engine = get_engine()
    migrations_dir = get_settings().migrations_dir

    with engine.begin() as conn:
        conn.exec_driver_sql(
            "CREATE TABLE IF NOT EXISTS public.schema_migrations ("
            "version text PRIMARY KEY, applied_at timestamptz NOT NULL DEFAULT now())"
        )
        already_applied = {
            row[0] for row in conn.execute(text("SELECT version FROM public.schema_migrations"))
        }

    files = sorted(p for p in migrations_dir.glob("*.sql") if _MIGRATION_NAME_RE.match(p.name))
    applied: list[str] = []
    for path in files:
        match = _MIGRATION_NAME_RE.match(path.name)
        assert match is not None  # filtered by the glob comprehension above
        if target is not None and match.group(1) > target:
            break
        if path.name in already_applied:
            continue
        sql = path.read_text(encoding="utf-8")
        with engine.begin() as conn:
            conn.exec_driver_sql(sql)
            conn.execute(
                text("INSERT INTO public.schema_migrations (version) VALUES (:v)"),
                {"v": path.name},
            )
        applied.append(path.name)
        logger.info("migration applied", extra={"migration": path.name})

    return MigrationReport(applied=applied, already_up_to_date=len(applied) == 0)
