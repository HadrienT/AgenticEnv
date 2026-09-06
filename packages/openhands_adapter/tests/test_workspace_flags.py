from __future__ import annotations

import subprocess
from typing import Any

import pytest
from openhands_adapter.docker_workspace import AgenticEnvDockerWorkspace

_IMAGE = "ghcr.io/openhands/agent-server:1.21.0-python"


def _ok(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="deadbeef\n", stderr="")


def _capture_docker_run(monkeypatch: pytest.MonkeyPatch) -> list[list[str]]:
    """Patches `execute_command` (so no real `docker` process runs) and
    `_wait_for_health` (a real HTTP poll) before construction, so building an
    `AgenticEnvDockerWorkspace` drives the real `model_post_init` ->
    `_start_container` path -- exercising the actual flag-construction logic
    under test, not a hand-rolled call to a private method."""
    calls: list[list[str]] = []

    def fake_execute_command(
        cmd: list[str], *args: Any, **kwargs: Any
    ) -> subprocess.CompletedProcess[str]:
        calls.append(cmd)
        return _ok(cmd)

    monkeypatch.setattr("openhands_adapter.docker_workspace.execute_command", fake_execute_command)
    monkeypatch.setattr(
        AgenticEnvDockerWorkspace, "_wait_for_health", lambda self, timeout=120.0: None
    )
    return calls


def test_start_container_adds_host_docker_internal_gateway(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _capture_docker_run(monkeypatch)

    AgenticEnvDockerWorkspace(server_image=_IMAGE, host_port=39001, detach_logs=False)

    run_cmd = calls[-1]
    assert "--add-host" in run_cmd
    assert run_cmd[run_cmd.index("--add-host") + 1] == "host.docker.internal:host-gateway"
    assert "-p" in run_cmd
    assert run_cmd[run_cmd.index("-p") + 1] == "39001:8000"


def test_start_container_passes_gpu_and_volume_flags(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _capture_docker_run(monkeypatch)

    AgenticEnvDockerWorkspace(
        server_image=_IMAGE,
        host_port=39002,
        detach_logs=False,
        enable_gpu=True,
        volumes=["/host/path:/container/path"],
    )

    run_cmd = calls[-1]
    assert "--gpus" in run_cmd
    assert run_cmd[run_cmd.index("--gpus") + 1] == "all"
    assert "-v" in run_cmd
    assert run_cmd[run_cmd.index("-v") + 1] == "/host/path:/container/path"


def test_start_container_raises_when_docker_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_execute_command(
        cmd: list[str], *args: Any, **kwargs: Any
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(args=cmd, returncode=1, stdout="", stderr="not found")

    monkeypatch.setattr("openhands_adapter.docker_workspace.execute_command", fake_execute_command)

    with pytest.raises(RuntimeError, match="Docker is not available"):
        AgenticEnvDockerWorkspace(server_image=_IMAGE, host_port=39003, detach_logs=False)
