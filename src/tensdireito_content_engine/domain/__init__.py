"""Núcleo de domínio: tipos e entidades independentes de persistência."""

from tensdireito_content_engine.domain.enums import (
    DocumentKind,
    EditorialStatus,
    EndpointStatus,
    EndpointType,
    EntityType,
    EvidenceStance,
    ImpactType,
    LegalStage,
    RegistryStatus,
    SourceTier,
    VerificationStatus,
)
from tensdireito_content_engine.domain.event import Event
from tensdireito_content_engine.domain.raw_item import RawItem
from tensdireito_content_engine.domain.sources import (
    SourceDocument,
    SourceEndpoint,
    SourceEvidence,
    SourceRegistry,
)
from tensdireito_content_engine.domain.validation import DomainValidationError

__all__ = [
    "DocumentKind",
    "DomainValidationError",
    "EditorialStatus",
    "EndpointStatus",
    "EndpointType",
    "EntityType",
    "Event",
    "EvidenceStance",
    "ImpactType",
    "LegalStage",
    "RawItem",
    "RegistryStatus",
    "SourceDocument",
    "SourceEndpoint",
    "SourceEvidence",
    "SourceRegistry",
    "SourceTier",
    "VerificationStatus",
]
