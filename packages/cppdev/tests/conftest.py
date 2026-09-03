from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def cmake_project(tmp_path: Path) -> Path:
    """A minimal real CMake + CTest project, configured with the Makefiles generator."""
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.cpp").write_text(
        '#include <cstdio>\nint main() { std::printf("hello\\n"); return 0; }\n',
        encoding="utf-8",
    )
    (tmp_path / "CMakeLists.txt").write_text(
        "cmake_minimum_required(VERSION 3.20)\n"
        "project(fixture LANGUAGES CXX)\n"
        "add_executable(hello src/main.cpp)\n"
        "enable_testing()\n"
        "add_test(NAME hello_runs COMMAND hello)\n",
        encoding="utf-8",
    )
    (tmp_path / "CMakePresets.json").write_text(
        '{"version": 3, "configurePresets": [{"name": "dev", "generator": "Unix Makefiles", '
        '"binaryDir": "${sourceDir}/build/dev"}]}',
        encoding="utf-8",
    )
    return tmp_path
