"""Modelo de fontes em quatro conceitos (DEC-007, SOURCES.md §2, DATA_MODEL.md §2.1, §2.5).

- `SourceRegistry`: quem publica e que confiança merece (tier).
- `SourceEndpoint`: onde e como se obtém informação dessa fonte.
- `SourceDocument`: o documento concreto obtido (versão normalizada).
- `SourceEvidence`: excerto literal de um documento ligado a uma claim.

Apenas modelos de domínio: não há recolha, HTTP, parsing nem validação externa.
"""

import re
from dataclasses import dataclass
from datetime import datetime

from tensdireito_content_engine.domain.enums import (
    DocumentKind,
    DocumentStatus,
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
    optional_id,
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

_SHA256_HEX = re.compile(r"[0-9a-f]{64}")
_LANGUAGE = re.compile(r"[a-z]{2,3}")
# Nome de anfitrião (sem esquema, porta, caminho nem IP literal), em minúsculas.
_HOST = re.compile(
    r"(?=.*[a-z])[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?(\.[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?)+"
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
    # DEC-065/066: anfitriões exactos para onde se aceita um redirect (vazio = nenhum) e a
    # excepção do Bing, em que um 302/307 é limitação. Não se combinam.
    redirect_hosts: tuple[str, ...] = ()
    redirect_is_throttle: bool = False

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
        require_text_tuple(self.redirect_hosts, "redirect_hosts")
        for host in self.redirect_hosts:
            if not _HOST.fullmatch(host):
                raise DomainValidationError(
                    f"redirect_hosts só aceita nomes de anfitrião em minúsculas: {host!r}"
                )
        if not isinstance(self.redirect_is_throttle, bool):
            raise DomainValidationError("redirect_is_throttle tem de ser bool")
        if self.redirect_hosts and self.redirect_is_throttle:
            raise DomainValidationError("redirect_hosts e redirect_is_throttle não se combinam")

        if self.endpoint_status in (EndpointStatus.VALIDATED, EndpointStatus.ACTIVE):
            _require_manual_validation(self.validated_at, self.validated_by)


@dataclass(frozen=True, slots=True, kw_only=True)
class SourceDocument:
    """Documento normalizado, Nível 2 (DATA_MODEL.md §2.1; DEC-037 a DEC-041).

    `id` é atribuído pela base de dados (nulo antes da escrita); `created_in_run`
    pertence à persistência e não está aqui, como em `RawItem`.
    """

    raw_item_id: int
    title: str
    source_tier: SourceTier
    status: DocumentStatus
    id: int | None = None
    source_id: str | None = None  # nulo quando a fonte não foi resolvida
    canonical_url: str | None = None  # nulo = por calcular, D12 OPEN (DEC-037)
    text: str | None = None  # nulo = sem texto útil, nunca fabricado (DEC-040)
    language: str | None = None  # nulo = desconhecida, nunca presumida (DEC-038)
    published_at: datetime | None = None  # nunca inventada
    document_kind: DocumentKind | None = None  # nulo = não determinado (DEC-039)
    text_hash: str | None = None  # nulo se e só se `text` é nulo
    duplicate_of: int | None = None  # representante com o mesmo `text_hash` (DEC-022)

    def __post_init__(self) -> None:
        optional_id(self.id, "id")
        require_id(self.raw_item_id, "raw_item_id")
        require_text(self.title, "title")
        require_member(self.source_tier, SourceTier, "source_tier")
        require_member(self.status, DocumentStatus, "status")
        optional_text(self.source_id, "source_id")
        optional_text(self.canonical_url, "canonical_url")
        optional_text(self.text, "text")
        optional_text(self.language, "language")
        optional_utc(self.published_at, "published_at")
        if self.document_kind is not None:
            require_member(self.document_kind, DocumentKind, "document_kind")
        optional_text(self.text_hash, "text_hash")
        optional_id(self.duplicate_of, "duplicate_of")

        if self.source_id is None and self.source_tier is not SourceTier.T4:
            raise DomainValidationError("um documento sem fonte resolvida é T4 (SOURCES.md §3.4)")
        if (self.text is None) != (self.text_hash is None):
            raise DomainValidationError("text e text_hash são ambos nulos ou ambos preenchidos")
        if self.text_hash is not None and not _SHA256_HEX.fullmatch(self.text_hash):
            raise DomainValidationError(
                f"text_hash tem de ser SHA-256 hexadecimal em minúsculas: {self.text_hash!r}"
            )
        if self.language is not None and not _LANGUAGE.fullmatch(self.language):
            raise DomainValidationError(
                f"language tem de ter 2 ou 3 letras ASCII minúsculas: {self.language!r}"
            )
        if self.duplicate_of is not None:
            if self.status is not DocumentStatus.IGNORED:
                raise DomainValidationError("um documento com duplicate_of tem status ignored")
            if self.text_hash is None:
                raise DomainValidationError("um documento com duplicate_of tem text_hash")


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
