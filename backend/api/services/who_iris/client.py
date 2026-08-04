from uuid import UUID

import requests

from api.config import config
from api.services.who_iris.models import (
    WhoIrisBitstream,
    WhoIrisBitstreamsResponse,
    WhoIrisBundlesResponse,
    WhoIrisItem,
    WhoIrisSearchResponse,
    WhoPublication,
    WhoPublicationContentResponse,
    WhoPublicationDocument,
    WhoPublicationSearchResponse,
)
from api.utils.http import fetch_validated_json

MAX_DOCUMENTS = 3
MAX_BYTES_PER_DOCUMENT = 12_000


class WhoIrisService:
    def __init__(
        self,
        *,
        base_url: str = config.WHO_IRIS_API_BASE_URL,
        user_agent: str = f"HumConnect/1.0 (+{config.APP_URL})",
        timeout_seconds: float = config.WHO_IRIS_TIMEOUT_SECONDS,
        max_documents: int = config.WHO_IRIS_MAX_DOCUMENTS,
        excerpt_bytes: int = config.WHO_IRIS_EXCERPT_BYTES,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._headers = {"User-Agent": user_agent}
        self._timeout_seconds = timeout_seconds
        self._max_documents = max_documents
        self._excerpt_bytes = excerpt_bytes

    def search(self, query: str, limit: int) -> WhoPublicationSearchResponse:
        response = fetch_validated_json(
            self._url("discover/search/objects"),
            WhoIrisSearchResponse,
            params={
                "query": query,
                "dsoType": "ITEM",
                "page": 0,
                "size": limit,
            },
            headers=self._headers,
            timeout_seconds=self._timeout_seconds,
            malformed_payload_message=("WHO IRIS returned a malformed search payload."),
        )
        return WhoPublicationSearchResponse(
            query=query,
            total=response.total_elements(),
            results=[WhoPublication.from_item(item) for item in response.items()],
        )

    def get_item(self, item_id: UUID) -> WhoIrisItem:
        return fetch_validated_json(
            self._url(f"core/items/{item_id}"),
            WhoIrisItem,
            headers=self._headers,
            timeout_seconds=self._timeout_seconds,
            malformed_payload_message="WHO IRIS returned a malformed item payload.",
        )

    def list_text_documents(self, item_id: UUID) -> list[WhoIrisBitstream]:
        bundles = fetch_validated_json(
            self._url(f"core/items/{item_id}/bundles"),
            WhoIrisBundlesResponse,
            headers=self._headers,
            timeout_seconds=self._timeout_seconds,
            malformed_payload_message=(
                "WHO IRIS returned a malformed bundle list payload."
            ),
        )
        documents: list[WhoIrisBitstream] = []
        for bundle in bundles.embedded.bundles:
            if bundle.name.upper() != "TEXT":
                continue
            bitstreams = fetch_validated_json(
                self._url(f"core/bundles/{bundle.uuid}/bitstreams"),
                WhoIrisBitstreamsResponse,
                headers=self._headers,
                timeout_seconds=self._timeout_seconds,
                malformed_payload_message=(
                    "WHO IRIS returned a malformed TEXT document list payload."
                ),
            )
            documents.extend(bitstreams.embedded.bitstreams)
        return documents

    def read_excerpt(
        self,
        document_id: UUID,
        *,
        max_bytes: int = MAX_BYTES_PER_DOCUMENT,
    ) -> str:
        response = requests.get(
            self._url(f"core/bitstreams/{document_id}/content"),
            headers={
                **self._headers,
                "Range": f"bytes=0-{max_bytes - 1}",
            },
            timeout=self._timeout_seconds,
        )
        response.raise_for_status()
        return response.content[:max_bytes].decode("utf-8", errors="replace")

    def get_publication_content(
        self,
        item_id: UUID,
    ) -> WhoPublicationContentResponse:
        item = self.get_item(item_id)
        all_documents = sorted(
            self.list_text_documents(item_id),
            key=lambda document: document.name,
        )
        documents = [
            WhoPublicationDocument(
                filename=document.name,
                content=self.read_excerpt(
                    document.id,
                    max_bytes=self._excerpt_bytes,
                ),
                truncated=document.size_bytes > self._excerpt_bytes,
            )
            for document in all_documents[: self._max_documents]
        ]

        warnings: list[str] = []
        if not documents:
            warnings.append(
                "WHO IRIS has no extracted text for this publication. "
                "Use the source URL to access the original document."
            )
        if len(all_documents) > self._max_documents:
            omitted_count = len(all_documents) - self._max_documents
            warnings.append(f"Omitted {omitted_count} additional document(s).")

        return WhoPublicationContentResponse(
            item_id=item.id,
            title=item.publication_title(),
            source_url=item.public_url(),
            documents=documents,
            warnings=warnings,
        )

    def _url(self, path: str) -> str:
        return f"{self._base_url}/{path.lstrip('/')}"
