"""Enumerações de domínio decididas no M1.

Fonte: DATA_MODEL.md §2–3, EDITORIAL_POLICY.md §4.3, SOURCES.md §2–3 e
DEC-003, DEC-005, DEC-007, DEC-012. Convenção (DATA_MODEL.md): os estados escritos
em maiúsculas na documentação são armazenados em minúsculas.

`VerificationStatus`, `LegalStage` e `ImpactType` são dimensões independentes:
nenhuma deriva das outras.
"""

from enum import StrEnum


class VerificationStatus(StrEnum):
    """Nível de confirmação de claims e eventos (DEC-003)."""

    UNVERIFIED = "unverified"
    VERIFIED_EDITORIAL = "verified_editorial"
    VERIFIED_OFFICIAL = "verified_official"
    CONTRADICTED = "contradicted"


class LegalStage(StrEnum):
    """Fase em que está a medida (DEC-005, DATA_MODEL.md §3.3)."""

    NOT_APPLICABLE = "not_applicable"
    PROPOSAL = "proposal"
    ANNOUNCEMENT = "announcement"
    APPROVED = "approved"
    PUBLISHED = "published"
    IN_FORCE = "in_force"
    ENDED = "ended"


class ImpactType(StrEnum):
    """O que muda para o cidadão (EDITORIAL_POLICY.md §4.3)."""

    NEW_RIGHT = "new_right"
    RIGHT_CHANGE = "right_change"
    AMOUNT_CHANGE = "amount_change"
    NEW_OBLIGATION = "new_obligation"
    OBLIGATION_CHANGE = "obligation_change"
    DEADLINE = "deadline"
    PROCEDURE_CHANGE = "procedure_change"
    PAYMENT_SCHEDULE = "payment_schedule"
    MEASURE_ENDING = "measure_ending"
    INFORMATIONAL = "informational"
    OTHER = "other"


class EditorialStatus(StrEnum):
    """Ponto do circuito editorial de um evento (DEC-012, DATA_MODEL.md §3.5)."""

    CANDIDATE = "candidate"
    REJECT = "reject"
    WATCHLIST = "watchlist"
    EDITORIAL_REVIEW = "editorial_review"
    READY_FOR_APPROVAL = "ready_for_approval"
    APPROVED = "approved"
    PUBLISHED = "published"  # reservado; a V1 nunca o atribui
    ARCHIVED = "archived"


class SourceTier(StrEnum):
    """Hierarquia de confiança das fontes (SOURCES.md §3)."""

    T1 = "T1"
    T2 = "T2"
    T3 = "T3"
    T4 = "T4"


class EntityType(StrEnum):
    PUBLIC_BODY = "public_body"
    OFFICIAL_JOURNAL = "official_journal"
    GOVERNMENT = "government"
    PARLIAMENT = "parliament"
    SPECIALISED = "specialised"
    PRESS = "press"
    SOCIAL = "social"
    OTHER = "other"


class RegistryStatus(StrEnum):
    CANDIDATE = "candidate"
    VALIDATED = "validated"
    INACTIVE = "inactive"


class EndpointType(StrEnum):
    RSS = "rss"
    HTML_PAGE = "html_page"
    MANUAL = "manual"


class EndpointStatus(StrEnum):
    CANDIDATE = "candidate"
    VALIDATED = "validated"
    ACTIVE = "active"
    INACTIVE = "inactive"


class DocumentKind(StrEnum):
    LEGAL_TEXT = "legal_text"
    CONSOLIDATED_LEGAL_TEXT = "consolidated_legal_text"
    OFFICIAL_PAGE = "official_page"
    OFFICIAL_COMMUNICATION = "official_communication"
    NEWS = "news"
    ANALYSIS = "analysis"
    SOCIAL_POST = "social_post"
    OTHER = "other"


class EvidenceStance(StrEnum):
    SUPPORTS = "supports"
    CONTRADICTS = "contradicts"
    CONTEXT = "context"
