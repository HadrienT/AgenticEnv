from __future__ import annotations

import re

import pytest
from corelib.errors import ConfigError
from openhands_adapter.profiles import DEFAULT_PROFILE, list_profiles, load_profile, repo_notes


def test_every_shipped_profile_loads_with_its_prompt() -> None:
    assert DEFAULT_PROFILE in list_profiles()
    for name in list_profiles():
        profile = load_profile(name)
        assert profile.prompt()


def test_coding_has_the_terminal_and_only_its_allowlisted_tools() -> None:
    profile = load_profile("coding")

    allowed = re.compile(profile.tools_regex)

    assert "terminal" in profile.builtin_tools
    assert allowed.fullmatch("kb.search")
    assert allowed.fullmatch("finish")
    assert not allowed.fullmatch("kb_search")
    assert not allowed.fullmatch("cpp.bench")


def test_research_cannot_run_commands() -> None:
    assert "terminal" not in load_profile("research").builtin_tools


def test_unknown_profile_names_the_available_ones() -> None:
    with pytest.raises(ConfigError) as caught:
        load_profile("nope")
    assert "coding" in caught.value.details["available"]


def test_repo_notes_prefers_agents_md_and_is_bounded(tmp_path) -> None:  # type: ignore[no-untyped-def]
    assert repo_notes(None) is None
    assert repo_notes(str(tmp_path)) is None

    (tmp_path / "CLAUDE.md").write_text("claude")
    assert "claude" in (repo_notes(str(tmp_path)) or "")

    (tmp_path / "AGENTS.md").write_text("x" * 100_000)
    notes = repo_notes(str(tmp_path)) or ""
    assert 'source="AGENTS.md"' in notes
    assert len(notes) < 20_000
