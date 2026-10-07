"""`Event` — a unidade editorial (DATA_MODEL.md §2.2, EDITORIAL_POLICY.md §10, DEC-010).

Um evento representa um assunto editorial, não uma notícia. Fontes, documentos,
evidências e actualizações ligam-se ao mesmo evento; nova cobertura não cria um
evento novo. Esta classe só garante invariantes locais: o cálculo de
`verification_status` (etapa VERIFY), as transições editoriais e o agrupamento
pertencem a etapas futuras.
"""

from dataclasses import dataclass
from datetime import date, datetime

from tensdireito_content_engine.domain.enums import (
    EditorialStatus,
    ImpactType,
    LegalStage,
    VerificationStatus,
)
from tensdireito_content_engine.domain.validation import (
    DomainValidationError,
    optional_id,
    optional_text,
    optional_utc,
    require_id,
    require_member,
    require_text,
    require_text_tuple,
    require_utc,
)

# Estados em que `audience` pode estar vazia (DEC-019): o candidato ainda incompleto
# e os estados terminais. Todos os outros exigem ≥1 audiência.
AUDIENCE_OPTIONAL_STATUSES = frozenset(
    {EditorialStatus.CANDIDATE, EditorialStatus.REJECT, EditorialStatus.ARCHIVED}
)


@dataclass(frozen=True, slots=True, kw_only=True)
class Event:
    # Identificação
    id: int

    # Informação editorial (interna)
    title: str
    summary: str | None = None

    # Classificação (códigos da taxonomia — EDITORIAL_POLICY.md §4)
    category: str
    subcategory: str | None = None
    secondary_categories: tuple[str, ...] = ()
    audience: tuple[str, ...] = ()

    # Impacto
    impact_type: ImpactType

    # Estado jurídico
    legal_stage: LegalStage
    official_reference: str | None = None
    effective_date: date | None = None
    deadline: date | None = None

    # Verificação — calculada pela etapa VERIFY, nunca decidida pela IA
    verification_status: VerificationStatus = VerificationStatus.UNVERIFIED
    verification_notes: str | None = None

    # Estado editorial
    editorial_status: EditorialStatus = EditorialStatus.CANDIDATE
    status_reason: str | None = None

    # Relações entre eventos
    merged_into: int | None = None
    related_events: tuple[int, ...] = ()

    # Timestamps (UTC)
    first_seen_at: datetime
    last_seen_at: datetime
    last_material_change_at: datetime | None = None

    def __post_init__(self) -> None:
        require_id(self.id, "id")
        require_text(self.title, "title")
        optional_text(self.summary, "summary")

        require_text(self.category, "category")
        optional_text(self.subcategory, "subcategory")
        require_text_tuple(self.secondary_categories, "secondary_categories")
        if self.category in self.secondary_categories:
            raise DomainValidationError("secondary_categories não pode repetir category")
        require_text_tuple(self.audience, "audience")

        require_member(self.impact_type, ImpactType, "impact_type")
        require_member(self.legal_stage, LegalStage, "legal_stage")
        optional_text(self.official_reference, "official_reference")
        for name in ("effective_date", "deadline"):
            value = getattr(self, name)
            if value is not None and (not isinstance(value, date) or isinstance(value, datetime)):
                raise DomainValidationError(f"{name} tem de ser date")

        require_member(self.verification_status, VerificationStatus, "verification_status")
        optional_text(self.verification_notes, "verification_notes")

        require_member(self.editorial_status, EditorialStatus, "editorial_status")
        optional_text(self.status_reason, "status_reason")
        if self.editorial_status is EditorialStatus.REJECT and self.status_reason is None:
            raise DomainValidationError("um evento REJECT exige status_reason")
        if not self.audience and self.editorial_status not in AUDIENCE_OPTIONAL_STATUSES:
            raise DomainValidationError(
                f"um evento {self.editorial_status.name} exige pelo menos uma audiência"
            )

        optional_id(self.merged_into, "merged_into")
        if self.merged_into is not None:
            if self.merged_into == self.id:
                raise DomainValidationError("um evento não pode ser fundido em si próprio")
            if self.editorial_status is not EditorialStatus.ARCHIVED:
                raise DomainValidationError("um evento fundido (merged_into) tem de estar ARCHIVED")
        if not isinstance(self.related_events, tuple):
            raise DomainValidationError("related_events tem de ser tuple")
        for related in self.related_events:
            require_id(related, "related_events")
        if self.id in self.related_events:
            raise DomainValidationError("related_events não pode conter o próprio evento")
        if len(set(self.related_events)) != len(self.related_events):
            raise DomainValidationError("related_events não pode ter valores repetidos")

        require_utc(self.first_seen_at, "first_seen_at")
        require_utc(self.last_seen_at, "last_seen_at")
        optional_utc(self.last_material_change_at, "last_material_change_at")
        if self.last_seen_at < self.first_seen_at:
            raise DomainValidationError("last_seen_at não pode ser anterior a first_seen_at")

    @property
    def legal_stage_officially_confirmed(self) -> bool:
        """True só se o `legal_stage` puder ser tratado como facto jurídico (DEC-020).

        Fora de `VERIFIED_OFFICIAL` o estágio é de trabalho (proposto ou apenas
        parcialmente confirmado); `not_applicable` não tem estágio a confirmar.
        """
        return (
            self.verification_status is VerificationStatus.VERIFIED_OFFICIAL
            and self.legal_stage is not LegalStage.NOT_APPLICABLE
        )
