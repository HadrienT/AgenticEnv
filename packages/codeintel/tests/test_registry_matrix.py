from __future__ import annotations

from pathlib import Path
from typing import Any

from codeintel.registry_matrix import registry_matrix
from codeintel.schemas import RegistryCombination, RegistryMatrixRequest

_KEY_ENUMS = {"InstrumentKind": "instrument", "ModelKind": "model", "EngineKind": "engine"}


def _enumerator(name: str, enum: str) -> dict[str, Any]:
    return {
        "kind": "DeclRef",
        "detail": name,
        "children": [{"kind": "Type", "children": [{"kind": "Enum", "detail": enum}]}],
    }


def _registration(line: int, instrument: str, model: str, engine: str) -> dict[str, Any]:
    """The shape clangd really returns for `r.register_pricer({...}, lambda)`."""
    return {
        "kind": "CXXMemberCall",
        "range": {"start": {"line": line, "character": 12}},
        "children": [
            {"kind": "Member", "detail": "register_pricer", "children": []},
            {
                "kind": "MaterializeTemporary",
                "children": [
                    {
                        "kind": "InitList",
                        "children": [
                            _enumerator(instrument, "InstrumentKind"),
                            _enumerator(model, "ModelKind"),
                            _enumerator(engine, "EngineKind"),
                        ],
                    }
                ],
            },
            {
                "kind": "Lambda",
                "children": [_enumerator("Analytic", "EngineKind")],
            },
        ],
    }


def _matrix(project: Path, client: Any, **kwargs: Any) -> Any:
    return registry_matrix(
        RegistryMatrixRequest(paths=["src/registry.cpp"]),
        root=project,
        compile_commands_dir=project / "build",
        timeout_s=5.0,
        function_names=["register_pricer"],
        key_enums=_KEY_ENUMS,
        client=client,
        **kwargs,
    )


def test_reads_the_key_from_the_enumerators_of_the_call(cpp_project: Path, fake_client) -> None:
    (cpp_project / "src" / "registry.cpp").write_text("// registrations\n", encoding="utf-8")
    fake_client.ast_result = {
        "kind": "TranslationUnitDecl",
        "children": [_registration(57, "EquityVanillaOption", "BlackScholes", "MonteCarlo")],
    }

    report = _matrix(cpp_project, fake_client)

    entry = report.entries[0]
    assert (entry.instrument, entry.model, entry.engine) == (
        "EquityVanillaOption",
        "BlackScholes",
        "MonteCarlo",
    )
    assert entry.adapter == "src/registry.cpp:58"


def test_reports_expected_combinations_that_are_missing(cpp_project: Path, fake_client) -> None:
    (cpp_project / "src" / "registry.cpp").write_text("// registrations\n", encoding="utf-8")
    fake_client.ast_result = {
        "kind": "TranslationUnitDecl",
        "children": [_registration(1, "EquityVanillaOption", "BlackScholes", "Analytic")],
    }
    wanted = RegistryCombination(instrument="Barrier", model="BlackScholes", engine="MonteCarlo")

    report = _matrix(cpp_project, fake_client, expected_combinations=[wanted])

    assert report.missing_combinations == [wanted]


def test_other_calls_are_ignored(cpp_project: Path, fake_client) -> None:
    (cpp_project / "src" / "registry.cpp").write_text("// registrations\n", encoding="utf-8")
    fake_client.ast_result = {
        "kind": "TranslationUnitDecl",
        "children": [
            {"kind": "CallExpr", "children": [{"kind": "DeclRef", "detail": "something_else"}]}
        ],
    }

    assert _matrix(cpp_project, fake_client).entries == []
