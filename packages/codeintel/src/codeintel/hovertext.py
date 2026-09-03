from __future__ import annotations

from typing import Any


def hover_to_signature_and_doc(hover: dict[str, Any] | None) -> tuple[str | None, str | None]:
    """clangd's hover text is a fenced code block (the signature) followed by prose (the doc)."""
    if hover is None:
        return None, None
    value = _hover_text(hover.get("contents"))
    if value is None:
        return None, None
    return _split_signature_and_doc(value)


def _hover_text(contents: Any) -> str | None:
    if isinstance(contents, dict):
        value = contents.get("value")
        return str(value) if value is not None else None
    if isinstance(contents, str):
        return contents
    if isinstance(contents, list):
        parts = [c.get("value") if isinstance(c, dict) else c for c in contents]
        joined = "\n".join(str(p) for p in parts if p)
        return joined or None
    return None


def _split_signature_and_doc(value: str) -> tuple[str | None, str | None]:
    lines = value.splitlines()
    if lines and lines[0].startswith("```"):
        try:
            end = lines.index("```", 1)
        except ValueError:
            end = len(lines)
        signature = "\n".join(lines[1:end]).strip() or None
        rest = "\n".join(lines[end + 1 :]).strip() or None
        return signature, rest
    return None, value.strip() or None
