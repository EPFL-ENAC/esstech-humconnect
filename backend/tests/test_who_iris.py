import asyncio
import json
import os
from uuid import UUID, uuid4

import pytest
import requests

os.environ.setdefault("DB_USER", "test")
os.environ.setdefault("DB_PASSWORD", "test")
os.environ.setdefault("OPENAI_API_URL", "http://test.local")
os.environ.setdefault("OPENAI_API_KEY", "test")
os.environ.setdefault("OPENAI_API_KEY_PREMIUM", "test")
os.environ.setdefault("MEDITRON_MCP_API_KEY", "test")
os.environ.setdefault("KEYCLOAK_API_ID", "test")
os.environ.setdefault("KEYCLOAK_API_SECRET", "test")

from api.services.chat_room.humconnect_assistant import BASE_INSTRUCTIONS
from api.services.chat_room.tools import (
    GET_WHO_PUBLICATION_CONTENT_TOOL,
    SEARCH_WHO_PUBLICATIONS_TOOL,
)
from api.services.chat_room.tools import who_iris as who_iris_tool_module
from api.services.who_iris import client as who_iris_client_module
from api.services.who_iris.client import WhoIrisService
from api.services.who_iris.models import (
    WhoIrisBitstream,
    WhoIrisItem,
    WhoIrisMetadataValue,
    WhoPublication,
    WhoPublicationContentResponse,
    WhoPublicationSearchResponse,
)
from api.utils import http as http_utils

ITEM_ID = UUID("c8e4cbaa-edb7-4ed7-ab12-db9440e5cee0")
BUNDLE_ID = UUID("24cf7eeb-0071-460a-afda-17ed6c8b8b6c")
DOCUMENT_ID = UUID("e2784f5a-3a05-4c72-89d2-271fc3e875df")


class FakeResponse:
    def __init__(self, payload=None, *, content=b"", status_code=200):
        self._payload = payload
        self.content = content
        self.status_code = status_code

    def json(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")


def metadata_value(value):
    return {"value": value}


def item_payload(*, metadata=None):
    return {
        "uuid": str(ITEM_ID),
        "name": "Fallback title",
        "handle": "10665/386858",
        "metadata": metadata or {},
    }


def search_payload(items, *, total=None):
    return {
        "_embedded": {
            "searchResult": {
                "_embedded": {
                    "objects": [
                        {"_embedded": {"indexableObject": item}} for item in items
                    ]
                },
                "page": {"totalElements": len(items) if total is None else total},
            }
        }
    }


def make_item():
    return WhoIrisItem.model_validate(
        item_payload(
            metadata={
                "dc.title": [metadata_value("Evaluation: annual report")],
                "dc.identifier.uri": [
                    metadata_value("https://iris.who.int/handle/10665/386858")
                ],
            }
        )
    )


def make_document(name, size_bytes, document_id=None):
    return WhoIrisBitstream(
        uuid=document_id or uuid4(),
        name=name,
        sizeBytes=size_bytes,
    )


def test_search_requests_items_and_normalizes_hal_metadata(monkeypatch):
    calls = []
    payload = search_payload(
        [
            item_payload(
                metadata={
                    "dc.title": [metadata_value("Cholera vaccines: WHO position")],
                    "dc.description.abstract": [metadata_value("WHO abstract")],
                    "dc.contributor.author": [
                        metadata_value("World Health Organization")
                    ],
                    "dc.date.issued": [metadata_value("2026-08-03")],
                    "dc.language.iso": [metadata_value("en")],
                    "dc.subject": [metadata_value("Cholera")],
                    "dc.subject.mesh": [metadata_value("Vaccination")],
                    "dc.type": [metadata_value("Technical documents")],
                    "dc.identifier.uri": [
                        metadata_value("https://iris.who.int/handle/10665/386858")
                    ],
                }
            )
        ],
        total=42,
    )

    def fake_get(url, *, params, headers, timeout):
        calls.append((url, params, headers, timeout))
        return FakeResponse(payload)

    monkeypatch.setattr(http_utils.requests, "get", fake_get)

    result = WhoIrisService(
        base_url="https://iris.test/server/api/",
        user_agent="HumConnect/Test",
        timeout_seconds=7,
    ).search("cholera vaccination", 5)

    assert calls == [
        (
            "https://iris.test/server/api/discover/search/objects",
            {
                "query": "cholera vaccination",
                "dsoType": "ITEM",
                "page": 0,
                "size": 5,
            },
            {"User-Agent": "HumConnect/Test"},
            7,
        )
    ]
    assert result.model_dump(mode="json") == {
        "query": "cholera vaccination",
        "total": 42,
        "results": [
            {
                "item_id": str(ITEM_ID),
                "title": "Cholera vaccines: WHO position",
                "abstract": "WHO abstract",
                "authors": ["World Health Organization"],
                "published_date": "2026-08-03",
                "languages": ["en"],
                "subjects": ["Cholera", "Vaccination"],
                "document_types": ["Technical documents"],
                "source_url": "https://iris.who.int/handle/10665/386858",
            }
        ],
    }


def test_search_handles_missing_optional_metadata_and_empty_results(monkeypatch):
    responses = iter(
        [
            FakeResponse(search_payload([item_payload()])),
            FakeResponse(search_payload([], total=0)),
        ]
    )
    monkeypatch.setattr(
        http_utils.requests,
        "get",
        lambda *args, **kwargs: next(responses),
    )
    service = WhoIrisService()

    missing = service.search("unknown", 1)
    empty = service.search("nothing", 5)

    assert missing.results[0].model_dump(mode="json") == {
        "item_id": str(ITEM_ID),
        "title": "Fallback title",
        "abstract": None,
        "authors": [],
        "published_date": None,
        "languages": [],
        "subjects": [],
        "document_types": [],
        "source_url": "https://iris.who.int/handle/10665/386858",
    }
    assert empty.total == 0
    assert empty.results == []


@pytest.mark.parametrize(
    "payload",
    [None, [], {}, {"_embedded": {"searchResult": {}}}],
)
def test_search_rejects_malformed_payloads(monkeypatch, payload):
    monkeypatch.setattr(
        http_utils.requests,
        "get",
        lambda *args, **kwargs: FakeResponse(payload),
    )

    with pytest.raises(ValueError, match="malformed search payload"):
        WhoIrisService().search("cholera", 5)


@pytest.mark.parametrize("error", [requests.Timeout("slow"), requests.HTTPError("bad")])
def test_search_propagates_http_failures(monkeypatch, error):
    if isinstance(error, requests.Timeout):
        monkeypatch.setattr(
            http_utils.requests,
            "get",
            lambda *args, **kwargs: (_ for _ in ()).throw(error),
        )
    else:
        monkeypatch.setattr(
            http_utils.requests,
            "get",
            lambda *args, **kwargs: FakeResponse({}, status_code=500),
        )

    with pytest.raises(type(error)):
        WhoIrisService().search("cholera", 5)


def test_list_text_documents_ignores_non_text_bundles(monkeypatch):
    calls = []

    def fake_get(url, *, params, headers, timeout):
        calls.append(url)
        if url.endswith(f"/items/{ITEM_ID}/bundles"):
            return FakeResponse(
                {
                    "_embedded": {
                        "bundles": [
                            {"uuid": str(uuid4()), "name": "ORIGINAL"},
                            {"uuid": str(BUNDLE_ID), "name": "TEXT"},
                        ]
                    }
                }
            )
        return FakeResponse(
            {
                "_embedded": {
                    "bitstreams": [
                        {
                            "uuid": str(DOCUMENT_ID),
                            "name": "report.pdf.txt",
                            "sizeBytes": 19_956,
                        }
                    ]
                }
            }
        )

    monkeypatch.setattr(http_utils.requests, "get", fake_get)

    documents = WhoIrisService().list_text_documents(ITEM_ID)

    assert [document.id for document in documents] == [DOCUMENT_ID]
    assert len(calls) == 2
    assert calls[1].endswith(f"/bundles/{BUNDLE_ID}/bitstreams")


@pytest.mark.parametrize("status_code", [200, 206])
def test_read_excerpt_uses_range_and_slices_full_responses(monkeypatch, status_code):
    calls = []

    def fake_get(url, *, headers, timeout):
        calls.append((url, headers, timeout))
        return FakeResponse(content=(b"x" * 20_000), status_code=status_code)

    monkeypatch.setattr(who_iris_client_module.requests, "get", fake_get)

    excerpt = WhoIrisService(
        user_agent="HumConnect/Test",
        timeout_seconds=4,
    ).read_excerpt(
        DOCUMENT_ID,
        max_bytes=12_000,
    )

    assert len(excerpt.encode()) == 12_000
    assert calls == [
        (
            f"https://iris.who.int/server/api/core/bitstreams/{DOCUMENT_ID}/content",
            {
                "User-Agent": "HumConnect/Test",
                "Range": "bytes=0-11999",
            },
            4,
        )
    ]


def test_content_orders_caps_and_warns_about_documents(monkeypatch):
    service = WhoIrisService(max_documents=3, excerpt_bytes=12_000)
    documents = [
        make_document("z-annex.txt", 4),
        make_document("a-report.txt", 12_001),
        make_document("m-table.txt", 12_000),
        make_document("b-appendix.txt", 20_000),
    ]
    monkeypatch.setattr(service, "get_item", lambda item_id: make_item())
    monkeypatch.setattr(service, "list_text_documents", lambda item_id: documents)
    monkeypatch.setattr(
        service,
        "read_excerpt",
        lambda document_id, *, max_bytes: f"excerpt:{document_id}:{max_bytes}",
    )

    result = service.get_publication_content(ITEM_ID)

    assert [document.filename for document in result.documents] == [
        "a-report.txt",
        "b-appendix.txt",
        "m-table.txt",
    ]
    assert [document.truncated for document in result.documents] == [True, True, False]
    assert all(document.content.endswith(":12000") for document in result.documents)
    assert result.warnings == ["Omitted 1 additional document(s)."]


@pytest.mark.parametrize("document_count", [1, 2])
def test_content_returns_all_available_documents_without_warning(
    monkeypatch, document_count
):
    service = WhoIrisService()
    documents = [
        make_document(f"document-{index}.txt", 10) for index in range(document_count)
    ]
    monkeypatch.setattr(service, "get_item", lambda item_id: make_item())
    monkeypatch.setattr(service, "list_text_documents", lambda item_id: documents)
    monkeypatch.setattr(service, "read_excerpt", lambda *args, **kwargs: "excerpt")

    result = service.get_publication_content(ITEM_ID)

    assert len(result.documents) == document_count
    assert result.warnings == []


def test_content_without_extracted_text_returns_source_warning(monkeypatch):
    service = WhoIrisService()
    monkeypatch.setattr(service, "get_item", lambda item_id: make_item())
    monkeypatch.setattr(service, "list_text_documents", lambda item_id: [])

    result = service.get_publication_content(ITEM_ID)

    assert result.documents == []
    assert result.source_url == "https://iris.who.int/handle/10665/386858"
    assert result.warnings == [
        "WHO IRIS has no extracted text for this publication. "
        "Use the source URL to access the original document."
    ]


@pytest.mark.parametrize(
    ("tool", "arguments", "message"),
    [
        (SEARCH_WHO_PUBLICATIONS_TOOL, {}, "invalid query data"),
        (SEARCH_WHO_PUBLICATIONS_TOOL, {"query": ""}, "invalid query data"),
        (
            SEARCH_WHO_PUBLICATIONS_TOOL,
            {"query": "cholera", "limit": 11},
            "invalid query data",
        ),
        (
            SEARCH_WHO_PUBLICATIONS_TOOL,
            {"query": "cholera", "unexpected": True},
            "invalid query data",
        ),
        (
            GET_WHO_PUBLICATION_CONTENT_TOOL,
            {"item_id": "not-a-uuid"},
            "invalid item ID",
        ),
    ],
)
def test_who_tools_reject_invalid_input(tool, arguments, message):
    with pytest.raises(ValueError, match=message):
        asyncio.run(tool.execute(arguments))


def test_search_tool_uses_default_limit_and_serializes_result(monkeypatch):
    calls = []

    class FakeService:
        def search(self, query, limit):
            calls.append((query, limit))
            return WhoPublicationSearchResponse(
                query=query,
                total=1,
                results=[
                    WhoPublication(
                        item_id=ITEM_ID,
                        title="Publication",
                        abstract=None,
                        authors=[],
                        published_date=None,
                        languages=[],
                        subjects=[],
                        document_types=[],
                        source_url="https://iris.test/publication",
                    )
                ],
            )

    monkeypatch.setattr(who_iris_tool_module, "WhoIrisService", FakeService)

    async def run():
        return await SEARCH_WHO_PUBLICATIONS_TOOL.execute(
            {"query": "cholera vaccination"},
            None,
        )

    output = asyncio.run(run())

    assert calls == [("cholera vaccination", 5)]
    assert json.loads(output)["results"][0]["item_id"] == str(ITEM_ID)


def test_content_tool_accepts_json_uuid_and_serializes_result(monkeypatch):
    calls = []

    class FakeService:
        def get_publication_content(self, item_id):
            calls.append(item_id)
            return WhoPublicationContentResponse(
                item_id=item_id,
                title="Publication",
                source_url="https://iris.test/publication",
                documents=[],
                warnings=["No text"],
            )

    monkeypatch.setattr(who_iris_tool_module, "WhoIrisService", FakeService)

    async def run():
        return await GET_WHO_PUBLICATION_CONTENT_TOOL.execute(
            {"item_id": str(ITEM_ID)},
            None,
        )

    output = asyncio.run(run())

    assert calls == [ITEM_ID]
    assert json.loads(output)["warnings"] == ["No text"]


def test_who_tools_are_registered_and_routed():
    from api.services.chat_room.default_tool_set import DEFAULT_LOCAL_TOOLS

    names = [tool.name for tool in DEFAULT_LOCAL_TOOLS]
    assert "search_who_publications" in names
    assert "get_who_publication_content" in names
    assert "WHO guidance" in BASE_INSTRUCTIONS
    assert "get_humanitarian_context for recent outbreaks" in BASE_INSTRUCTIONS
