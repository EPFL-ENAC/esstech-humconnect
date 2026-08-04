from pydantic import BaseModel

from api.utils import http as http_utils
from api.utils.http import fetch_validated_json


class ExampleResponse(BaseModel):
    value: str


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload
        self.raise_for_status_called = False

    def raise_for_status(self):
        self.raise_for_status_called = True

    def json(self):
        return self.payload


def test_get_validated_json_requests_and_validates_payload(monkeypatch):
    calls = []
    response = FakeResponse({"value": "ok"})

    def fake_get(url, *, params, headers, timeout):
        calls.append((url, params, headers, timeout))
        return response

    monkeypatch.setattr(http_utils.requests, "get", fake_get)

    result = fetch_validated_json(
        "https://example.test/data",
        ExampleResponse,
        params={"limit": 3},
        headers={"User-Agent": "HumConnect/1.0"},
        timeout_seconds=4,
        malformed_payload_message="Malformed example payload.",
    )

    assert result == ExampleResponse(value="ok")
    assert response.raise_for_status_called is True
    assert calls == [
        (
            "https://example.test/data",
            {"limit": 3},
            {"User-Agent": "HumConnect/1.0"},
            4,
        )
    ]


def test_get_validated_json_uses_caller_error_message(monkeypatch):
    monkeypatch.setattr(
        http_utils.requests,
        "get",
        lambda *args, **kwargs: FakeResponse({"unexpected": True}),
    )

    try:
        fetch_validated_json(
            "https://example.test/data",
            ExampleResponse,
            timeout_seconds=4,
            malformed_payload_message="Malformed example payload.",
        )
    except ValueError as exc:
        assert str(exc) == "Malformed example payload."
    else:
        raise AssertionError("Expected malformed payload validation to fail.")
