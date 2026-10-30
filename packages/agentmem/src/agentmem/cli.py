"""`agentmem` CLI: see what the agent remembers, and make it forget (WP14 §2)."""

from __future__ import annotations

import argparse
import sys

from corelib.db import session_scope
from sqlalchemy import text


def _cmd_list(_args: argparse.Namespace) -> int:
    with session_scope() as session:
        rows = session.execute(
            text("SELECT episode_id, started_at, status, goal FROM mem.episodes ORDER BY 2 DESC")
        ).all()
    for row in rows:
        print(f"{row.episode_id}  {row.started_at:%Y-%m-%d}  {row.status:9}  {row.goal[:80]}")
    return 0


def _cmd_forget(args: argparse.Namespace) -> int:
    with session_scope() as session:
        session.execute(
            text("DELETE FROM mem.episode_actions WHERE episode_id = :id"), {"id": args.episode_id}
        )
        session.execute(
            text("DELETE FROM mem.artifacts WHERE episode_id = :id"), {"id": args.episode_id}
        )
        deleted = session.execute(
            text("DELETE FROM mem.episodes WHERE episode_id = :id"), {"id": args.episode_id}
        ).rowcount  # type: ignore[attr-defined]
    print("forgotten" if deleted else "no such episode")
    return 0 if deleted else 1


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="agentmem")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("list", help="List remembered episodes").set_defaults(func=_cmd_list)
    forget = commands.add_parser("forget", help="Delete one episode")
    forget.add_argument("episode_id")
    forget.set_defaults(func=_cmd_forget)
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])
    sys.exit(args.func(args))
