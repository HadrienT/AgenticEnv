from __future__ import annotations

import re
from pathlib import Path

_SRC = Path(__file__).parent.parent / "src" / "cppdev"
_FORBIDDEN = re.compile(
    r"\b(black_scholes|heston|sabr|implied_vol|discount_curve)\b", re.IGNORECASE
)


def test_cppdev_never_reimplements_pricing_logic() -> None:
    for path in _SRC.rglob("*.py"):
        content = path.read_text(encoding="utf-8")
        assert not _FORBIDDEN.search(content), f"pricing vocabulary found in {path}"
