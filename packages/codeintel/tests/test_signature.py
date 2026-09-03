from __future__ import annotations

from pathlib import Path

from codeintel.schemas import SignatureRequest
from codeintel.signature import signature


def test_signature_from_hover(cpp_project: Path, fake_client) -> None:
    fake_client.hover_result = {"contents": {"value": "```cpp\nint foo()\n```\nDoc text."}}
    report = signature(
        SignatureRequest(file="src/foo.cpp", line=3, column=5),
        root=cpp_project,
        compile_commands_dir=cpp_project / "build",
        timeout_s=5.0,
        client=fake_client,
    )
    assert report.ok is True
    assert report.signature == "int foo()"
    assert report.documentation == "Doc text."


def test_signature_no_hover(cpp_project: Path, fake_client) -> None:
    fake_client.hover_result = None
    report = signature(
        SignatureRequest(file="src/foo.cpp", line=3, column=5),
        root=cpp_project,
        compile_commands_dir=cpp_project / "build",
        timeout_s=5.0,
        client=fake_client,
    )
    assert report.ok is False
