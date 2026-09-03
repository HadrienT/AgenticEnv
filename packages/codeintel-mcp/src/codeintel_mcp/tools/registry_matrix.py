from __future__ import annotations

from pathlib import Path
from typing import Any

from codeintel.registry_matrix import registry_matrix as run_registry_matrix
from codeintel.schemas import RegistryMatrixRequest
from corelib.config import load_yaml_config

from codeintel_mcp.schemas import CodeintelConfig
from codeintel_mcp.tools.dispatch import dispatch


def registry_matrix(
    root: str, paths: list[str] | None = None, max_results: int = 500, build_dir: str = "build/dev"
) -> dict[str, Any]:
    """The real `(instrument, model, engine)` registration matrix, AST-extracted, never by regex."""

    def _run(timeout_s: int) -> dict[str, Any]:
        config = load_yaml_config("codeintel.yaml", CodeintelConfig)
        report = run_registry_matrix(
            RegistryMatrixRequest(paths=paths or ["."], max_results=max_results),
            root=Path(root),
            compile_commands_dir=Path(root) / build_dir,
            timeout_s=float(timeout_s),
            function_names=config.registry_matrix.function_names,
            template_param_order=config.registry_matrix.template_param_order,
        )
        return report.model_dump(mode="json")

    return dispatch("code.registry_matrix", _run)
