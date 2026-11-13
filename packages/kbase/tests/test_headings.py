from __future__ import annotations

from kbase.ingestion.parsers.headings import HeadingPlan, plan_headings


def _levels(lines: list[str]) -> list[tuple[str, HeadingPlan]]:
    plan = plan_headings(lines)
    return [(lines[i], plan[i]) for i in sorted(plan)]


def test_flat_mineru_headings_are_rebuilt_from_numbering() -> None:
    lines = [
        "# Monte Carlo Methods",
        "# Generating Random Numbers",
        "## 2.1 Random Number Generation",
        "## 2.1.1 General Considerations",
        "## Skipping Ahead",
        "## 2.2 General Sampling Methods",
    ]
    assert [p.level for _, p in _levels(lines)] == [1, 2, 3, 4, 5, 3]


def test_running_headers_and_numeric_noise() -> None:
    lines = [
        "# Book",
        "## 2.3 Normal Random Variables",
        "## 2.3 Normal Random Variables",  # repeated as a page header
        "## 1, 3, 9, 5, 4, 1, ... ,",  # a sequence MinerU took for a heading
    ]
    actions = [p.action for _, p in _levels(lines)]
    assert actions == ["heading", "heading", "drop", "text"]


def test_consistent_levels_are_kept_as_written() -> None:
    lines = ["# Paper", "## Abstract", "## 1 Introduction", "### 1.1 Setting", "## Appendix"]
    assert [p.level for _, p in _levels(lines)] == [1, 2, 2, 3, 2]


def test_cfr_paragraph_ids_without_a_word_stay_headings() -> None:
    lines = ["# 12 CFR 217.132", "#### § 217.132(a)(1)", "text", "#### § 217.132(a)(1)(i)", "x"]
    plan = plan_headings(lines)
    assert plan[1].action == "heading" and plan[3].action == "heading"
