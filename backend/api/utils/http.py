from collections.abc import Mapping
from typing import TypeVar

import requests
from pydantic import BaseModel, ValidationError

ResponseModelT = TypeVar("ResponseModelT", bound=BaseModel)
RequestParamValue = str | int | float


def fetch_validated_json(
    url: str,
    model: type[ResponseModelT],
    *,
    timeout_seconds: float,
    malformed_payload_message: str,
    params: Mapping[str, RequestParamValue] | None = None,
    headers: Mapping[str, str] | None = None,
) -> ResponseModelT:
    if headers is None:
        response = requests.get(
            url,
            params=params,
            timeout=timeout_seconds,
        )
    else:
        response = requests.get(
            url,
            params=params,
            headers=headers,
            timeout=timeout_seconds,
        )
    response.raise_for_status()
    try:
        return model.model_validate(response.json())
    except (ValueError, ValidationError) as exc:
        raise ValueError(malformed_payload_message) from exc
