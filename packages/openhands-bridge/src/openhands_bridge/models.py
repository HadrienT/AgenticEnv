"""The model profiles of `configs/models.yaml`, for the client's model picker. One
model is loaded at a time, so `set_model` restarts llama-server for everybody."""

from __future__ import annotations

import asyncio

import yaml
from corelib.config import get_settings, repo_root
from corelib.errors import DependencyError, ValidationError

from openhands_bridge.protocol import ModelEntry

_SWITCH_COMMAND = ("sudo", "-n", "/usr/local/sbin/agx-llm-use")
_SWITCH_TIMEOUT_S = 180.0


def list_models() -> list[ModelEntry]:
    path = repo_root() / get_settings().configs_dir / "models.yaml"
    config = yaml.safe_load(path.read_text(encoding="utf-8"))
    served = get_settings().llm.served_model
    entries = []
    for profile, key in config["profiles"].items():
        model = config["models"].get(key)
        if model is None:
            continue
        entries.append(
            ModelEntry(
                id=profile,
                label=model["served_name"],
                context_window=model["ctx_size"],
                current=model["served_name"] == served,
                state="ready",
            )
        )
    return entries


async def switch_model(profile: str) -> None:
    """Same privileged switch as `just llm-use`, through the narrow sudoers rule."""
    if profile not in {entry.id for entry in list_models()}:
        raise ValidationError(f"unknown model profile: {profile}", details={"profile": profile})
    process = await asyncio.create_subprocess_exec(
        *_SWITCH_COMMAND,
        profile,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        _, stderr = await asyncio.wait_for(process.communicate(), _SWITCH_TIMEOUT_S)
    except TimeoutError as exc:
        process.kill()
        raise DependencyError(f"model switch to {profile} timed out") from exc
    if process.returncode != 0:
        raise DependencyError(
            f"model switch to {profile} failed: {stderr.decode(errors='replace').strip()}"
        )
