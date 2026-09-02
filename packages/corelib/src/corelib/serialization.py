from __future__ import annotations

import json
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel

from corelib.errors import ValidationError


class AppJSONEncoder(json.JSONEncoder):
    """Stable JSON encoding for Decimal, date/datetime, and numeric vectors."""

    def default(self, o: Any) -> Any:
        if isinstance(o, Decimal):
            return str(o)
        if isinstance(o, datetime):
            if o.tzinfo is None:
                raise ValidationError(
                    "cannot serialize a naive datetime", details={"value": repr(o)}
                )
            return o.isoformat()
        if isinstance(o, date):
            return o.isoformat()
        if isinstance(o, (tuple, set)):
            return list(o)
        return super().default(o)


def to_json(obj: Any) -> str:
    """Canonical JSON dump used for hashing, logging, and MCP responses."""
    return json.dumps(obj, cls=AppJSONEncoder, sort_keys=True)


def dto_to_dict(dto: BaseModel) -> dict[str, Any]:
    """`BaseModel` -> plain dict, JSON-mode (Decimal/date already stringified)."""
    return dto.model_dump(mode="json")


def dict_to_dto(data: dict[str, Any], model: type[BaseModel]) -> BaseModel:
    """Plain dict -> validated `BaseModel`; raises pydantic's `ValidationError` upstream."""
    return model.model_validate(data)
