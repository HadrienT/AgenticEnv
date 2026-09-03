from __future__ import annotations

from pathlib import Path
from typing import Any

from codeintel.client import ClangdClient
from codeintel.index import check_index_status
from codeintel.paths import from_uri, to_relative
from codeintel.positions import from_lsp_position, to_lsp_position
from codeintel.schemas import CallGraphNode, CallGraphReport, CallGraphRequest, Location
from codeintel.session import resolve_client


def call_graph(
    request: CallGraphRequest,
    *,
    root: Path,
    compile_commands_dir: Path,
    timeout_s: float,
    client: ClangdClient | None = None,
) -> CallGraphReport:
    """`callHierarchy/{incoming,outgoing}Calls`, breadth-bounded by `max_depth`/`max_results`."""
    index_info = check_index_status(root, compile_commands_dir)
    with resolve_client(root, compile_commands_dir, client=client) as session:
        uri = session.open_file(root / request.file, timeout_s=timeout_s)
        position = to_lsp_position(request.line, request.column)
        items = session.prepare_call_hierarchy(
            uri, position["line"], position["character"], timeout_s=timeout_s
        )
        if not items:
            return CallGraphReport(ok=False, index=index_info)
        # budget = [remaining node slots, omitted count]
        budget = [request.max_results, 0]
        root_node = _expand(
            session, items[0], request.direction, request.max_depth, root, timeout_s, budget
        )
    return CallGraphReport(ok=True, root=root_node, truncated=budget[1], index=index_info)


def _expand(
    session: ClangdClient,
    item: dict[str, Any],
    direction: str,
    remaining_depth: int,
    root: Path,
    timeout_s: float,
    budget: list[int],
) -> CallGraphNode:
    node = CallGraphNode(
        name=item.get("name", "?"), location=_item_location(item, root), children=[]
    )
    if remaining_depth <= 0:
        return node
    if direction == "callers":
        calls = session.incoming_calls(item, timeout_s=timeout_s)
        next_items = [call["from"] for call in calls]
    else:
        calls = session.outgoing_calls(item, timeout_s=timeout_s)
        next_items = [call["to"] for call in calls]
    for child_item in next_items:
        if budget[0] <= 0:
            budget[1] += 1
            continue
        budget[0] -= 1
        node.children.append(
            _expand(session, child_item, direction, remaining_depth - 1, root, timeout_s, budget)
        )
    return node


def _item_location(item: dict[str, Any], root: Path) -> Location:
    start = item["selectionRange"]["start"] if "selectionRange" in item else item["range"]["start"]
    line, column = from_lsp_position(start)
    return Location(file=to_relative(from_uri(item["uri"]), root), line=line, column=column)
