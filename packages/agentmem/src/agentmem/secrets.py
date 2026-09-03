"""Heuristic secret / host-path scrubbing for episodes (WP07 rule A4, 09-CONVENTIONS SEC6).

Best-effort pattern matching, applied as a backstop before persistence — it is not
a substitute for the agent simply never putting secrets in an episode. Findings are
reported as short labels only; the matched text itself is never echoed back (it
could itself be the secret)."""

from __future__ import annotations

import re

_SECRET_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"AKIA[0-9A-Z]{16}"),  # AWS access key id
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),  # PEM private key block
    re.compile(r"(?i)\b(api[_-]?key|secret|password|passwd|token)\b\s*[:=]\s*\S+"),
    re.compile(r"(?i)\bbearer\s+[a-z0-9._-]{20,}"),
    re.compile(r"\bsk-[A-Za-z0-9]{20,}\b"),  # OpenAI-style secret key
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"),  # GitHub token
)

_HOST_PATH_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"/home/[\w.-]+"),
    re.compile(r"/root(/|\b)"),
    re.compile(r"/Users/[\w.-]+"),
    re.compile(r"[A-Za-z]:\\Users\\[\w.-]+"),
)


def find_forbidden_patterns(*texts: str) -> list[str]:
    """Returns a de-duplicated list of finding labels (`"secret"` / `"host_path"`)."""
    findings: set[str] = set()
    for text in texts:
        if any(p.search(text) for p in _SECRET_PATTERNS):
            findings.add("secret")
        if any(p.search(text) for p in _HOST_PATH_PATTERNS):
            findings.add("host_path")
    return sorted(findings)
