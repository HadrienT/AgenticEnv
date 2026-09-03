from __future__ import annotations

from pathlib import Path

from cppdev.sanitize import _parse_findings


def test_asan_report_extracts_kind_message_and_project_only_frames() -> None:
    raw = (
        "==12345==ERROR: AddressSanitizer: heap-buffer-overflow on address 0xdead\n"
        "READ of size 4 at 0xdead thread T0\n"
        "    #0 0x1 in price(int*) /workspace/src/pricers/mc.cpp:42:10\n"
        "    #1 0x2 in main /workspace/src/main.cpp:10:5\n"
        "    #2 0x3 in __libc_start_main /usr/lib/libc.so.6+0x1\n"
    )

    findings = _parse_findings(raw, workspace_root=Path("/workspace"))

    assert len(findings) == 1
    assert findings[0].kind == "AddressSanitizer"
    assert findings[0].stack == ["src/pricers/mc.cpp:42", "src/main.cpp:10"]
    assert findings[0].frames_omitted == 1


def test_ubsan_report_extracts_file_and_line() -> None:
    raw = (
        "/workspace/src/utils/sobol.cpp:88:14: runtime error: signed integer overflow: "
        "2147483647 + 1 cannot be represented in type 'int'\n"
        "    #0 0x1 in advance() /workspace/src/utils/sobol.cpp:88:14\n"
    )

    findings = _parse_findings(raw, workspace_root=Path("/workspace"))

    assert len(findings) == 1
    assert findings[0].kind == "UndefinedBehaviorSanitizer"
    assert findings[0].file == "src/utils/sobol.cpp"
    assert findings[0].line == 88
