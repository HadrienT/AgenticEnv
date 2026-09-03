from __future__ import annotations

from agentmem.secrets import find_forbidden_patterns


def test_no_findings_on_clean_text() -> None:
    assert find_forbidden_patterns("calibrated Heston with RMSE 0.01") == []


def test_finds_aws_access_key() -> None:
    assert "secret" in find_forbidden_patterns("key is AKIAABCDEFGHIJKLMNOP")


def test_finds_private_key_block() -> None:
    pem = "-----BEGIN RSA PRIVATE KEY-----\nMIIB...\n-----END RSA PRIVATE KEY-----"
    assert "secret" in find_forbidden_patterns(pem)


def test_finds_api_key_assignment() -> None:
    assert "secret" in find_forbidden_patterns("api_key=sk-abcdefghijklmnopqrstuvwx")


def test_finds_bearer_token() -> None:
    assert "secret" in find_forbidden_patterns("Authorization: Bearer abcdefghijklmnopqrstuvwx")


def test_finds_host_path() -> None:
    assert "host_path" in find_forbidden_patterns("edited /home/alice/repo/file.py")


def test_finds_root_path() -> None:
    assert "host_path" in find_forbidden_patterns("wrote to /root/.ssh/config")


def test_multiple_texts_are_all_scanned() -> None:
    findings = find_forbidden_patterns("clean text", "token: abcdefghijklmnopqrstuvwxyz")
    assert "secret" in findings
