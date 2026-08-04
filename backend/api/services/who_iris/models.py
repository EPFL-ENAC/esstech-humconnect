from collections.abc import Sequence
from typing import Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

WHO_IRIS_PUBLIC_BASE_URL = "https://iris.who.int"


def _unique(values: Sequence[str]) -> list[str]:
    return list(dict.fromkeys(values))


class WhoIrisApiModel(BaseModel):
    """Permissive model for the evolving DSpace API response format."""

    model_config = ConfigDict(extra="allow")


class WhoIrisMetadataValue(WhoIrisApiModel):
    value: str | None = None


class WhoIrisItem(WhoIrisApiModel):
    uuid: UUID
    name: str | None = None
    handle: str | None = None
    metadata: dict[str, list[WhoIrisMetadataValue]] = Field(default_factory=dict)

    @property
    def id(self) -> UUID:
        return self.uuid

    def metadata_values(self, key: str) -> list[str]:
        return [
            entry.value.strip()
            for entry in self.metadata.get(key, [])
            if entry.value is not None and entry.value.strip()
        ]

    def first_metadata_value(self, key: str) -> str | None:
        values = self.metadata_values(key)
        return values[0] if values else None

    def publication_title(self) -> str:
        return self.first_metadata_value("dc.title") or self.name or "WHO publication"

    def public_url(self) -> str:
        canonical_url = self.first_metadata_value("dc.identifier.uri")
        if canonical_url:
            return canonical_url
        if self.handle:
            return f"{WHO_IRIS_PUBLIC_BASE_URL}/handle/{self.handle}"
        return f"{WHO_IRIS_PUBLIC_BASE_URL}/items/{self.uuid}"


class WhoIrisSearchObjectEmbedded(WhoIrisApiModel):
    indexable_object: WhoIrisItem = Field(alias="indexableObject")


class WhoIrisSearchObject(WhoIrisApiModel):
    embedded: WhoIrisSearchObjectEmbedded = Field(alias="_embedded")


class WhoIrisSearchObjectsEmbedded(WhoIrisApiModel):
    objects: list[WhoIrisSearchObject] = Field(default_factory=list)


class WhoIrisPage(WhoIrisApiModel):
    total_elements: int = Field(alias="totalElements")


class WhoIrisSearchResult(WhoIrisApiModel):
    embedded: WhoIrisSearchObjectsEmbedded = Field(alias="_embedded")
    page: WhoIrisPage


class WhoIrisSearchResponseEmbedded(WhoIrisApiModel):
    search_result: WhoIrisSearchResult = Field(alias="searchResult")


class WhoIrisSearchResponse(WhoIrisApiModel):
    embedded: WhoIrisSearchResponseEmbedded = Field(alias="_embedded")

    def items(self) -> list[WhoIrisItem]:
        return [
            result.embedded.indexable_object
            for result in self.embedded.search_result.embedded.objects
        ]

    def total_elements(self) -> int:
        return self.embedded.search_result.page.total_elements


class WhoIrisBundle(WhoIrisApiModel):
    uuid: UUID
    name: str


class WhoIrisBundlesEmbedded(WhoIrisApiModel):
    bundles: list[WhoIrisBundle] = Field(default_factory=list)


class WhoIrisBundlesResponse(WhoIrisApiModel):
    embedded: WhoIrisBundlesEmbedded = Field(alias="_embedded")


class WhoIrisBitstream(WhoIrisApiModel):
    uuid: UUID
    name: str
    size_bytes: int = Field(alias="sizeBytes", ge=0)

    @property
    def id(self) -> UUID:
        return self.uuid


class WhoIrisBitstreamsEmbedded(WhoIrisApiModel):
    bitstreams: list[WhoIrisBitstream] = Field(default_factory=list)


class WhoIrisBitstreamsResponse(WhoIrisApiModel):
    embedded: WhoIrisBitstreamsEmbedded = Field(alias="_embedded")


class WhoPublication(BaseModel):
    item_id: UUID
    title: str
    abstract: str | None
    authors: list[str]
    published_date: str | None
    languages: list[str]
    subjects: list[str]
    document_types: list[str]
    source_url: str

    @classmethod
    def from_item(cls, item: WhoIrisItem) -> Self:
        return cls(
            item_id=item.id,
            title=item.publication_title(),
            abstract=item.first_metadata_value("dc.description.abstract"),
            authors=item.metadata_values("dc.contributor.author"),
            published_date=item.first_metadata_value("dc.date.issued"),
            languages=_unique(
                item.metadata_values("dc.language.iso")
                + item.metadata_values("dc.language")
            ),
            subjects=_unique(
                item.metadata_values("dc.subject")
                + item.metadata_values("dc.subject.mesh")
            ),
            document_types=item.metadata_values("dc.type"),
            source_url=item.public_url(),
        )


class WhoPublicationSearchResponse(BaseModel):
    query: str
    total: int
    results: list[WhoPublication]


class WhoPublicationDocument(BaseModel):
    filename: str
    content: str
    truncated: bool


class WhoPublicationContentResponse(BaseModel):
    item_id: UUID
    title: str
    source_url: str
    documents: list[WhoPublicationDocument]
    warnings: list[str] = Field(default_factory=list)
