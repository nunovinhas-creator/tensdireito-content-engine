"""Modelo de fontes em quatro conceitos (DEC-007, SOURCES.md §2, DATA_MODEL.md §2.1, §2.5).

- `SourceRegistry`: quem publica e que confiança merece (tier).
- `SourceEndpoint`: onde e como se obtém informação dessa fonte.
- `SourceDocument`: o documento concreto obtido (versão normalizada).
- `SourceEvidence`: excerto literal de um documento ligado a uma claim.

Apenas modelos de domínio: não há recolha, HTTP, parsing nem validação externa.
"""

from dataclasses import dataclass
from datetime import datetime

from tensdireito_content_engine.domain.enums import (
    DocumentKind,
    EndpointStatus,
    EndpointType,
    EntityType,
    EvidenceStance,
    RegistryStatus,
    SourceTier,
)
from tensdireito_content_engine.domain.validation import (
    DomainValidationError,
    optional_human_actor,
    optional_text,
    optional_utc,
    require_human_actor,
    require_id,
    require_member,
    require_origin,
    require_text,
    require_text_tuple,
    require_utc,
)


@dataclass(frozen=True, slots=True, kw_only=True)
class SourceRegistry:
    id: str
    name: str
    entity_type: EntityType
    tier: SourceTier
    categories: tuple[str, ...] = ()
    domains: tuple[str, ...] = ()
    registry_status: RegistryStatus = RegistryStatus.CANDIDATE
    validated_at: datetime | None = None
    validated_by: str | None = None
    notes: str | None = None

    def __post_init__(self) -> None:
        require_text(self.id, "id")
        require_text(self.name, "name")
        require_member(self.entity_type, EntityType, "entity_type")
        require_member(self.tier, SourceTier, "tier")
        require_text_tuple(self.categories, "categories")
        require_text_tuple(self.domains, "domains")
        require_member(self.registry_status, RegistryStatus, "registry_status")
        optional_utc(self.validated_at, "validated_at")
        optional_human_actor(self.validated_by, "validated_by")
        optional_text(self.notes, "notes")

        if self.registry_status is RegistryStatus.CANDIDATE and self.domains:
            raise DomainValidationError("uma fonte CANDIDATE não pode ter domains")
        if self.registry_status is RegistryStatus.VALIDATED:
            _require_manual_validation(self.validated_at, self.validated_by)


@dataclass(frozen=True, slots=True, kw_only=True)
class SourceEndpoint:
    id: str
    source_id: str
    endpoint_type: EndpointType
    url: str | None = None  # nulo até validação; nunca preenchido por suposição
    endpoint_status: EndpointStatus = EndpointStatus.CANDIDATE
    validated_at: datetime | None = None
    validated_by: str | None = None
    last_success_at: datetime | None = None
    last_error: str | None = None

    def __post_init__(self) -> None:
        require_text(self.id, "id")
        require_text(self.source_id, "source_id")
        require_member(self.endpoint_type, EndpointType, "endpoint_type")
        optional_text(self.url, "url")
        require_member(self.endpoint_status, EndpointStatus, "endpoint_status")
        optional_utc(self.validated_at, "validated_at")
        optional_human_actor(self.validated_by, "validated_by")
        optional_utc(self.last_success_at, "last_success_at")
        optional_text(self.last_error, "last_error")

        if self.endpoint_status in (EndpointStatus.VALIDATED, EndpointStatus.ACTIVE):
            _require_manual_validation(self.validated_at, self.validated_by)


@dataclass(frozen=True, slots=True, kw_only=True)
class SourceDocument:
    id: int
    canonical_url: str
    title: str
    text: str
    language: str
    source_tier: SourceTier
    document_kind: DocumentKind
    source_id: str | None = None  # nulo quando a fonte não foi resolvida
    published_at: datetime | None = None  # nunca inventada

    def __post_init__(self) -> None:
        require_id(self.id, "id")
        require_text(self.canonical_url, "canonical_url")
        require_text(self.title, "title")
        require_text(self.text, "text")
        require_text(self.language, "language")
        require_member(self.source_tier, SourceTier, "source_tier")
        require_member(self.document_kind, DocumentKind, "document_kind")
        optional_text(self.source_id, "source_id")
        optional_utc(self.published_at, "published_at")

        if self.source_id is None and self.source_tier is not SourceTier.T4:
            raise DomainValidationError("um documento sem fonte resolvida é T4 (SOURCES.md §3.4)")


@dataclass(frozen=True, slots=True, kw_only=True)
class SourceEvidence:
    id: int
    claim_id: int
    source_document_id: int
    quote: str  # excerto literal
    stance: EvidenceStance
    source_tier: SourceTier
    document_kind: DocumentKind
    matched_by: str  # rules | human | llm:<prompt_id>
    quote_offset: int | None = None
    validated: bool = False  # true só se o excerto existir literalmente no documento

    def __post_init__(self) -> None:
        require_id(self.id, "id")
        require_id(self.claim_id, "claim_id")
        require_id(self.source_document_id, "source_document_id")
        require_text(self.quote, "quote")
        require_member(self.stance, EvidenceStance, "stance")
        require_member(self.source_tier, SourceTier, "source_tier")
        require_member(self.document_kind, DocumentKind, "document_kind")
        require_origin(self.matched_by, "matched_by")
        if self.quote_offset is not None and (
            not isinstance(self.quote_offset, int)
            or isinstance(self.quote_offset, bool)
            or self.quote_offset < 0
        ):
            raise DomainValidationError("quote_offset tem de ser um inteiro não negativo")
        if not isinstance(self.validated, bool):
            raise DomainValidationError("validated tem de ser bool")


def _require_manual_validation(validated_at: datetime | None, validated_by: str | None) -> None:
    """Validação manual registada: quando e por quem (SOURCES.md §4)."""
    if validated_at is None or validated_by is None:
        raise DomainValidationError("validação manual exige validated_at e validated_by")
    require_utc(validated_at, "validated_at")
    require_human_actor(validated_by, "validated_by")
