from __future__ import annotations

import json
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from corelib.errors import ValidationError
from corelib.serialization import dict_to_dto, dto_to_dict, to_json
from pydantic import BaseModel


class _Sample(BaseModel):
    name: str
    amount: Decimal


def test_to_json_encodes_decimal_as_string() -> None:
    encoded = to_json({"amount": Decimal("1.50")})
    assert json.loads(encoded) == {"amount": "1.50"}


def test_to_json_encodes_date_and_aware_datetime() -> None:
    payload = {
        "d": date(2026, 1, 1),
        "dt": datetime(2026, 1, 1, 12, 0, tzinfo=UTC),
    }
    decoded = json.loads(to_json(payload))
    assert decoded["d"] == "2026-01-01"
    assert decoded["dt"] == "2026-01-01T12:00:00+00:00"


def test_to_json_rejects_naive_datetime() -> None:
    with pytest.raises(ValidationError):
        to_json({"dt": datetime(2026, 1, 1)})


def test_to_json_encodes_vector_as_list() -> None:
    assert json.loads(to_json({"v": (1.0, 2.0, 3.0)})) == {"v": [1.0, 2.0, 3.0]}


def test_to_json_is_stable_across_key_order() -> None:
    assert to_json({"a": 1, "b": 2}) == to_json({"b": 2, "a": 1})


def test_dto_to_dict_and_back_roundtrip() -> None:
    dto = _Sample(name="x", amount=Decimal("2.00"))
    data = dto_to_dict(dto)
    assert data == {"name": "x", "amount": "2.00"}
    restored = dict_to_dto(data, _Sample)
    assert restored == dto
