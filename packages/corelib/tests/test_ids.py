from __future__ import annotations

from corelib.ids import deterministic_key, new_id, new_uuid7


def test_new_id_is_a_valid_uuid_string() -> None:
    import uuid

    value = new_id()
    assert uuid.UUID(value).version == 7


def test_new_uuid7_timestamp_prefix_is_monotonic() -> None:
    ids = [new_uuid7() for _ in range(50)]
    prefixes = [i.bytes[:6] for i in ids]
    assert prefixes == sorted(prefixes)


def test_new_uuid7_ids_are_unique() -> None:
    ids = {new_uuid7() for _ in range(100)}
    assert len(ids) == 100


def test_deterministic_key_normalizes_parts() -> None:
    assert deterministic_key("Heston", "1993") == "heston-1993"
