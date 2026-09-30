"""DB-side checks for healthcheck.sh: migrations + embeddings dimension.

Prints one `name|status|detail` line per check (the format healthcheck.sh
aggregates). Never raises: an unreachable DB or a missing package becomes a
`critical` line, so healthcheck.sh always gets both checks back.
"""

from __future__ import annotations


def _clean(detail: object) -> str:
    # One line, no `|` (field separator), no tabs/backslashes (raw into JSON).
    return " ".join(str(detail).replace("|", "/").replace("\\", "/").split())[:300]


def check_migrations() -> tuple[str, str]:
    from corelib.config import get_settings
    from corelib.db import _MIGRATION_NAME_RE, session_scope
    from sqlalchemy import text

    migrations_dir = get_settings().migrations_dir
    files = sorted(p.name for p in migrations_dir.glob("*.sql") if _MIGRATION_NAME_RE.match(p.name))
    with session_scope() as session:
        applied = {
            row[0] for row in session.execute(text("SELECT version FROM public.schema_migrations"))
        }
    pending = [f for f in files if f not in applied]
    if pending:
        return "critical", f"{len(pending)} pending: {', '.join(pending)} (run: just migrate)"
    return "ok", f"{len(files)} applied, latest {files[-1] if files else 'none'}"


def check_embeddings_dimension() -> tuple[str, str]:
    from corelib.db import session_scope
    from kbase.config import load_kbase_config
    from kbase.ingestion.writer import assert_dimension_matches

    dim = load_kbase_config().embeddings.dim
    with session_scope() as session:
        assert_dimension_matches(session, dim)
    return "ok", f"embeddings.dim={dim} matches kb.chunk_embeddings"


def main() -> None:
    for name, check in (
        ("migrations", check_migrations),
        ("embeddings_dimension", check_embeddings_dimension),
    ):
        try:
            status, detail = check()
        except Exception as exc:  # reported, never raised
            status, detail = "critical", f"{type(exc).__name__}: {exc}"
        print(f"{name}|{status}|{_clean(detail)}")


if __name__ == "__main__":
    main()
