"""Full-system smoke test: Docker agent-server sandbox + local llama-server.

Not run in CI (see `just test` / `just test-integration`, both deselect `e2e`;
blueprint/08-TESTING.md). Run manually on the real server:

    uv run pytest packages/openhands_adapter -m e2e -q

Prerequisites: llama-server up (`systemctl status llama-server`), the
llama-bridge proxy up (`systemctl status llama-bridge.socket`,
infra/scripts/render-llama-bridge.sh), Docker running, and
`ghcr.io/openhands/agent-server:1.21.0-python` pulled locally.
"""

from __future__ import annotations

import pytest

from openhands_adapter import run_task

pytestmark = pytest.mark.e2e


def test_run_task_reaches_local_llama_server_end_to_end() -> None:
    result = run_task("Réponds exactement : TEST_FINAL")

    assert result.final_text.strip() == "TEST_FINAL"
    assert result.execution_status == "finished"
    assert result.llm_source in {"create_payload", "switch_llm"}
