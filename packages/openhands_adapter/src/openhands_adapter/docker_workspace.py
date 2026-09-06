"""Docker workspace for the OpenHands agent-server sandbox (WP08b).

See blueprint/wp/WP08b-openhands-sandbox.md. This is the one place in the repo
allowed to import `openhands.*` (see the import-linter contract for
`openhands_adapter` in the root `pyproject.toml`).
"""

from __future__ import annotations

import os
import threading
import uuid
from typing import Any

from openhands.sdk.utils.command import execute_command
from openhands.workspace import DockerWorkspace


class AgenticEnvDockerWorkspace(DockerWorkspace):
    """`DockerWorkspace` with access to the host through `host.docker.internal`.

    `DockerWorkspace.model_validator` only requires `server_image` on the exact
    parent class (`self.__class__ is DockerWorkspace`); subclassing bypasses that
    guard, so callers of this class MUST pass `server_image` explicitly — see
    `openhands_adapter.session.AgentSession`, which sources it from
    `configs/openhands.yaml` (`sandbox.image`), pinned to the agent-server tag
    validated against the locally installed `openhands-sdk` version.
    """

    def _start_container(self, image: str, context: Any) -> None:
        self._image_name = image

        # Port used by the OpenHands agent-server on the host.
        if self.host_port is None:
            from openhands.workspace.docker.workspace import find_available_tcp_port

            self.host_port = find_available_tcp_port()
        else:
            self.host_port = int(self.host_port)

        from openhands.workspace.docker.workspace import check_port_available

        if not check_port_available(self.host_port):
            raise RuntimeError(f"Port {self.host_port} is not available")

        if self.extra_ports:
            if not check_port_available(self.host_port + 1):
                raise RuntimeError(f"Port {self.host_port + 1} is not available for VSCode")
            if not check_port_available(self.host_port + 2):
                raise RuntimeError(f"Port {self.host_port + 2} is not available for VNC")

        # Verify Docker.
        docker_ver = execute_command(["docker", "version"]).returncode
        if docker_ver != 0:
            raise RuntimeError("Docker is not available. Please install and start Docker.")

        flags: list[str] = []

        # Forward selected environment variables.
        for key in self.forward_env:
            if key in os.environ:
                flags += ["-e", f"{key}={os.environ[key]}"]

        # Volume mounts.
        for volume in self.volumes:
            flags += ["-v", volume]

        # Network path from sandbox -> host. Reaching the local llama-server
        # through this address requires the `llama-bridge` proxy (see
        # infra/systemd/llama-bridge.{socket,service}) — llama-server itself
        # stays bound to 127.0.0.1 only.
        flags += [
            "--add-host",
            "host.docker.internal:host-gateway",
        ]

        # Published agent-server port. host_port+1/+2 (VSCode/VNC, only when
        # extra_ports is set) are container-side dev ports unrelated to the
        # llama-bridge port configured in configs/openhands.yaml.
        ports = ["-p", f"{self.host_port}:8000"]

        if self.extra_ports:
            ports += [
                "-p",
                f"{self.host_port + 1}:8001",
                "-p",
                f"{self.host_port + 2}:8002",
            ]

        flags += ports

        if self.enable_gpu:
            flags += ["--gpus", "all"]

        container_name = f"agent-server-{uuid.uuid4()}"

        run_cmd = [
            "docker",
            "run",
            "-d",
            "--platform",
            self.platform,
            "--rm",
            "--ulimit",
            "nofile=65536:65536",
            "--name",
            container_name,
            *flags,
            image,
            "--host",
            "0.0.0.0",
            "--port",
            "8000",
        ]

        proc = execute_command(run_cmd)

        if proc.returncode != 0:
            raise RuntimeError(f"Failed to run docker container: {proc.stderr}")

        self._container_id = proc.stdout.strip()

        # Reuse OpenHands' existing log streaming.
        if self.detach_logs:
            self._logs_thread = threading.Thread(
                target=self._stream_docker_logs,
                daemon=True,
            )
            self._logs_thread.start()

        # RemoteWorkspace communicates with the agent-server through
        # the host-published port.
        object.__setattr__(
            self,
            "host",
            f"http://localhost:{self.host_port}",
        )
        object.__setattr__(self, "api_key", None)

        # Reuse OpenHands' existing health check.
        self._wait_for_health()

        # Initialize RemoteWorkspace internals.
        super(DockerWorkspace, self).model_post_init(context)
