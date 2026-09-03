from __future__ import annotations

import json
import re
from pathlib import Path

from cppdev.errors import ProjectDiscoveryError
from cppdev.runner import run_command
from cppdev.schemas import ProjectInfo

_VAR_RE = re.compile(r"\$\{source(?P<what>Dir|ParentDir)\}")


def _read_presets_file(root: Path, name: str) -> dict[str, object]:
    path = root / name
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ProjectDiscoveryError(f"invalid JSON in {name}", details={"file": name}) from exc
    if not isinstance(data, dict):
        raise ProjectDiscoveryError(f"{name} must contain a JSON object", details={"file": name})
    return data


def list_presets(root: Path) -> list[str]:
    """Names of every `configurePreset` from `CMakePresets.json` + `CMakeUserPresets.json`."""
    names: list[str] = []
    for filename in ("CMakePresets.json", "CMakeUserPresets.json"):
        data = _read_presets_file(root, filename)
        presets = data.get("configurePresets", [])
        if not isinstance(presets, list):
            continue
        for preset in presets:
            if isinstance(preset, dict) and isinstance(preset.get("name"), str):
                names.append(preset["name"])
    return names


def _resolve_binary_dir(binary_dir: str, root: Path) -> Path:
    def substitute(match: re.Match[str]) -> str:
        return str(root) if match.group("what") == "Dir" else str(root.parent)

    resolved = _VAR_RE.sub(substitute, binary_dir)
    if "$" in resolved:
        raise ProjectDiscoveryError(
            "unsupported CMakePresets.json macro in binaryDir; configure the preset "
            "explicitly first",
            details={"binaryDir": binary_dir},
        )
    return Path(resolved)


def resolve_build_dir(root: Path, preset: str) -> Path:
    """Best-effort resolution of a preset's `binaryDir`, supporting `${sourceDir}` macros."""
    for filename in ("CMakePresets.json", "CMakeUserPresets.json"):
        data = _read_presets_file(root, filename)
        entries = data.get("configurePresets", [])
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if isinstance(entry, dict) and entry.get("name") == preset:
                binary_dir = entry.get("binaryDir")
                if not isinstance(binary_dir, str):
                    raise ProjectDiscoveryError(
                        f"preset {preset!r} has no binaryDir", details={"preset": preset}
                    )
                return _resolve_binary_dir(binary_dir, root)
    raise ProjectDiscoveryError(f"unknown preset: {preset}", details={"preset": preset})


def list_targets(build_dir: Path, *, timeout_s: int = 30) -> list[str]:
    """Generator-agnostic target listing via the synthetic `help` target CMake always creates."""
    args = ["cmake", "--build", str(build_dir), "--target", "help"]
    result = run_command(args, cwd=build_dir, timeout_s=timeout_s)
    targets: list[str] = []
    for line in result.stdout.splitlines():
        stripped = line.strip()
        if stripped.startswith("...") and len(stripped) > 3:
            name = stripped[3:].strip()
            name = name.split(" ", 1)[0]
            if name:
                targets.append(name)
    return targets


def describe_project(root: Path, *, preset: str | None = None) -> ProjectInfo:
    """`cpp.targets`: presets, targets (if a configured preset is given), build state."""
    presets = list_presets(root)
    build_dir: Path | None = None
    targets: list[str] = []
    configured = False
    if preset is not None:
        build_dir = resolve_build_dir(root, preset)
        configured = (build_dir / "CMakeCache.txt").is_file()
        if configured:
            targets = list_targets(build_dir)
    return ProjectInfo(
        presets=presets,
        targets=targets,
        build_dir=str(build_dir) if build_dir is not None else None,
        configured=configured,
    )
