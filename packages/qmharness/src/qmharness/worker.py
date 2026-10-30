"""Runs in a child process: the only code that touches the `quantmodeling` extension.

A native module can hang without releasing the GIL or take the interpreter down with
a segfault, and an imported one stays cached past a rebuild. Keeping it in a process
of its own, one per run, makes all three harmless to the MCP server (WP15 §2). One
JSON request per stdin line, one JSON response per stdout line.
"""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path
from typing import Any

_INPUT_ALIASES = {"maturity_years": "maturity"}


def _build_input(module: Any, input_class: str, inputs: dict[str, Any]) -> Any:
    instance = getattr(module, input_class)()
    for name, value in inputs.items():
        if name == "option_type":
            instance.is_call = value == "call"
            continue
        field = _INPUT_ALIASES.get(name, name)
        if not hasattr(instance, field):
            raise ValueError(f"{input_class} has no field {field!r}")
        # Sweeps hand over floats; pybind11 refuses them for integer fields.
        setattr(instance, field, type(getattr(instance, field))(value))
    return instance


def _handle(module: Any, request: dict[str, Any]) -> Any:
    function = getattr(module, request["function"])
    if request["kind"] == "price":
        return function(_build_input(module, request["input_class"], request["inputs"]))
    return function(**request["params"])


def main() -> None:
    module_path = Path(sys.argv[1])
    sys.path.insert(0, str(module_path.parent))
    # The native module may print to stdout, which carries the responses.
    responses = sys.stdout
    sys.stdout = sys.stderr
    module = importlib.import_module("quantmodeling")
    for line in sys.stdin:
        try:
            response = {"ok": True, "result": _handle(module, json.loads(line))}
        except Exception as exc:  # noqa: BLE001 - reported to the parent, per request
            response = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
        responses.write(json.dumps(response) + "\n")
        responses.flush()


if __name__ == "__main__":
    main()
