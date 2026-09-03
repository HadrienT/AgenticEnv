from __future__ import annotations

from pathlib import Path

from codeintel.registry_matrix import registry_matrix
from codeintel.schemas import RegistryCombination, RegistryMatrixRequest


def test_registry_matrix_extracts_via_detail_regex(cpp_project: Path, fake_client) -> None:
    (cpp_project / "src" / "registrations.cpp").write_text(
        "void register_all() { registerPricer<EquityAsianOption, BlackScholes, MonteCarlo>(); }\n",
        encoding="utf-8",
    )
    fake_client.ast_result = {
        "role": "file",
        "kind": "TranslationUnitDecl",
        "range": {"start": {"line": 0, "character": 0}},
        "children": [
            {
                "role": "expression",
                "kind": "CallExpr",
                "detail": "registerPricer<EquityAsianOption, BlackScholes, MonteCarlo>(",
                "arcana": "",
                "range": {"start": {"line": 0, "character": 21}},
                "children": [],
            }
        ],
    }
    report = registry_matrix(
        RegistryMatrixRequest(paths=["src/registrations.cpp"]),
        root=cpp_project,
        compile_commands_dir=cpp_project / "build",
        timeout_s=5.0,
        function_names=["registerPricer"],
        template_param_order=["instrument", "model", "engine"],
        client=fake_client,
    )
    assert report.ok is True
    assert len(report.entries) == 1
    entry = report.entries[0]
    assert entry.instrument == "EquityAsianOption"
    assert entry.model == "BlackScholes"
    assert entry.engine == "MonteCarlo"
    assert entry.adapter.startswith("src/registrations.cpp:")


def test_registry_matrix_structural_fallback(cpp_project: Path, fake_client) -> None:
    (cpp_project / "src" / "registrations.cpp").write_text(
        "void register_all() {}\n", encoding="utf-8"
    )
    fake_client.ast_result = {
        "role": "file",
        "kind": "TranslationUnitDecl",
        "range": {"start": {"line": 0, "character": 0}},
        "children": [
            {
                "role": "expression",
                "kind": "CallExpr",
                "detail": "registerPricer(",
                "arcana": "",
                "range": {"start": {"line": 5, "character": 0}},
                "children": [
                    {"role": "template argument", "detail": "EquityAsianOption"},
                    {"role": "template argument", "detail": "BlackScholes"},
                    {"role": "template argument", "detail": "MonteCarlo"},
                ],
            }
        ],
    }
    report = registry_matrix(
        RegistryMatrixRequest(paths=["src/registrations.cpp"]),
        root=cpp_project,
        compile_commands_dir=cpp_project / "build",
        timeout_s=5.0,
        function_names=["registerPricer"],
        template_param_order=["instrument", "model", "engine"],
        client=fake_client,
    )
    assert len(report.entries) == 1
    assert report.entries[0].model == "BlackScholes"


def test_registry_matrix_reports_missing_combinations(cpp_project: Path, fake_client) -> None:
    (cpp_project / "src" / "registrations.cpp").write_text(
        "void register_all() {}\n", encoding="utf-8"
    )
    fake_client.ast_result = {"role": "file", "kind": "TranslationUnitDecl", "children": []}
    report = registry_matrix(
        RegistryMatrixRequest(paths=["src/registrations.cpp"]),
        root=cpp_project,
        compile_commands_dir=cpp_project / "build",
        timeout_s=5.0,
        function_names=["registerPricer"],
        template_param_order=["instrument", "model", "engine"],
        expected_combinations=[
            RegistryCombination(
                instrument="EquityAsianOption", model="BlackScholes", engine="MonteCarlo"
            )
        ],
        client=fake_client,
    )
    assert len(report.entries) == 0
    assert len(report.missing_combinations) == 1
