from __future__ import annotations

from importlib.machinery import EXTENSION_SUFFIXES
from pathlib import Path

import pytest
from qmharness.driver import build_fingerprint, find_module_file
from qmharness.errors import ModuleFingerprintError

_MODULE_NAME = f"quantmodeling{EXTENSION_SUFFIXES[0]}"


def _write_cmake_cache(build_dir: Path) -> None:
    build_dir.mkdir(parents=True, exist_ok=True)
    (build_dir / "CMakeCache.txt").write_text(
        "CMAKE_CXX_COMPILER:FILEPATH=/usr/bin/c++\n"
        "CMAKE_BUILD_TYPE:STRING=Release\n"
        "# a comment line, ignored\n",
        encoding="utf-8",
    )


def test_build_fingerprint_reads_cache_and_hashes_module(tmp_path: Path) -> None:
    root = tmp_path
    build_dir = tmp_path / "build"
    _write_cmake_cache(build_dir)
    module_dir = build_dir / "bindings" / "python"
    module_dir.mkdir(parents=True)
    module_file = module_dir / _MODULE_NAME
    module_file.write_bytes(b"fake shared object contents")

    def fake_run(args: list[str], cwd: Path) -> str:
        if args[:2] == ["git", "rev-parse"]:
            return "abc1234"
        if args[0] == "/usr/bin/c++":
            return "c++ (GCC) 13.2.0"
        raise AssertionError(f"unexpected command {args}")

    fingerprint = build_fingerprint(root, build_dir, "release", run=fake_run)
    assert fingerprint.commit == "abc1234"
    assert fingerprint.build_preset == "release"
    assert fingerprint.compiler == "/usr/bin/c++"
    assert fingerprint.optimization == "Release"
    assert fingerprint.module_path == str(module_file)
    assert len(fingerprint.module_sha256) == 64


def test_build_fingerprint_raises_without_cmake_cache(tmp_path: Path) -> None:
    with pytest.raises(ModuleFingerprintError):
        build_fingerprint(tmp_path, tmp_path / "build", "release", run=lambda a, c: "")


def test_build_fingerprint_raises_without_module_file(tmp_path: Path) -> None:
    build_dir = tmp_path / "build"
    _write_cmake_cache(build_dir)
    with pytest.raises(ModuleFingerprintError):
        build_fingerprint(
            tmp_path, build_dir, "release", run=lambda a, c: "abc1234" if "rev-parse" in a else ""
        )


def test_find_module_file_needs_a_module_for_this_python(tmp_path: Path) -> None:
    (tmp_path / "quantmodeling.cpython-39-x86_64-linux-gnu.so").write_bytes(b"")

    with pytest.raises(ModuleFingerprintError):
        find_module_file(tmp_path)
