import dataclasses
from datetime import UTC, date, datetime, timedelta, timezone

import pytest

from tensdireito_content_engine.domain import (
    DomainValidationError,
    EditorialStatus,
    Event,
    ImpactType,
    LegalStage,
    VerificationStatus,
)

T0 = datetime(2026, 10, 1, 9, 0, tzinfo=UTC)


def make_event(**overrides) -> Event:
    fields = {
        "id": 1,
        "title": "Actualização do valor de uma prestação em 2027",
        "category": "seguranca_social",
        "audience": ("beneficiarios_prestacoes",),
        "impact_type": ImpactType.AMOUNT_CHANGE,
        "legal_stage": LegalStage.ANNOUNCEMENT,
        "first_seen_at": T0,
        "last_seen_at": T0,
    }
    fields.update(overrides)
    return Event(**fields)


def test_valid_event():
    event = make_event(
        summary="Resumo interno.",
        subcategory="indexantes de referência",
        secondary_categories=("pensoes_reformas",),
        effective_date=date(2027, 1, 1),
        related_events=(2,),
        last_seen_at=T0 + timedelta(days=1),
        last_material_change_at=T0,
    )
    assert event.id == 1
    assert event.category == "seguranca_social"


def test_event_starts_unverified_and_candidate():
    event = make_event()
    assert event.verification_status is VerificationStatus.UNVERIFIED
    assert event.editorial_status is EditorialStatus.CANDIDATE


def test_event_is_immutable():
    event = make_event()
    with pytest.raises(dataclasses.FrozenInstanceError):
        event.verification_status = VerificationStatus.VERIFIED_OFFICIAL  # type: ignore[misc]


@pytest.mark.parametrize("stage", list(LegalStage))
def test_legal_stage_does_not_change_verification_status(stage):
    event = make_event(legal_stage=stage)
    assert event.verification_status is VerificationStatus.UNVERIFIED
    updated = dataclasses.replace(event, legal_stage=LegalStage.IN_FORCE)
    assert updated.verification_status is event.verification_status


@pytest.mark.parametrize("impact", list(ImpactType))
def test_impact_type_does_not_change_verification_status_or_legal_stage(impact):
    event = make_event(impact_type=impact)
    assert event.verification_status is VerificationStatus.UNVERIFIED
    assert event.legal_stage is LegalStage.ANNOUNCEMENT


def test_verification_status_does_not_change_legal_stage():
    event = make_event(verification_status=VerificationStatus.VERIFIED_EDITORIAL)
    assert event.legal_stage is LegalStage.ANNOUNCEMENT


@pytest.mark.parametrize(
    "value",
    ["verified", "partially_verified", "not_applicable", "verified_official", None],
)
def test_unknown_or_untyped_verification_status_is_rejected(value):
    with pytest.raises(DomainValidationError):
        make_event(verification_status=value)


def test_legal_stage_cannot_be_used_as_verification_status():
    with pytest.raises(DomainValidationError):
        make_event(verification_status=LegalStage.APPROVED)


def test_impact_type_cannot_be_used_as_legal_stage():
    with pytest.raises(DomainValidationError):
        make_event(legal_stage=ImpactType.DEADLINE)
    with pytest.raises(DomainValidationError):
        make_event(impact_type=LegalStage.PUBLISHED)


@pytest.mark.parametrize("field", ["title", "category"])
@pytest.mark.parametrize("value", ["", "   ", None])
def test_required_text_cannot_be_empty(field, value):
    with pytest.raises(DomainValidationError):
        make_event(**{field: value})


@pytest.mark.parametrize("field", ["summary", "subcategory", "status_reason"])
def test_optional_text_cannot_be_blank_when_given(field):
    with pytest.raises(DomainValidationError):
        make_event(**{field: " "})


@pytest.mark.parametrize("value", [0, -1, True, "1"])
def test_id_must_be_positive_int(value):
    with pytest.raises(DomainValidationError):
        make_event(id=value)


def test_timestamps_must_be_utc():
    with pytest.raises(DomainValidationError):
        make_event(first_seen_at=datetime(2026, 10, 1, 9, 0))
    with pytest.raises(DomainValidationError):
        make_event(last_seen_at=datetime(2026, 10, 1, 9, 0, tzinfo=timezone(timedelta(hours=1))))


def test_last_seen_cannot_precede_first_seen():
    with pytest.raises(DomainValidationError):
        make_event(last_seen_at=T0 - timedelta(seconds=1))


def test_reject_requires_status_reason():
    with pytest.raises(DomainValidationError):
        make_event(editorial_status=EditorialStatus.REJECT)
    event = make_event(editorial_status=EditorialStatus.REJECT, status_reason="out_of_scope")
    assert event.status_reason == "out_of_scope"


def test_merged_event_must_be_archived_and_not_self():
    with pytest.raises(DomainValidationError):
        make_event(merged_into=2)
    with pytest.raises(DomainValidationError):
        make_event(merged_into=1, editorial_status=EditorialStatus.ARCHIVED)
    event = make_event(merged_into=2, editorial_status=EditorialStatus.ARCHIVED)
    assert event.merged_into == 2


def test_related_events_cannot_contain_self_or_repeat():
    with pytest.raises(DomainValidationError):
        make_event(related_events=(1,))
    with pytest.raises(DomainValidationError):
        make_event(related_events=(2, 2))


def test_secondary_categories_cannot_repeat_main_category():
    with pytest.raises(DomainValidationError):
        make_event(secondary_categories=("seguranca_social",))


def test_classification_lists_must_be_tuples_of_text():
    with pytest.raises(DomainValidationError):
        make_event(audience=["pensionistas"])
    with pytest.raises(DomainValidationError):
        make_event(audience=("pensionistas", ""))


def test_dates_must_be_dates_not_datetimes():
    with pytest.raises(DomainValidationError):
        make_event(deadline=T0)


# --- DEC-019: audience -----------------------------------------------------

AUDIENCE_REQUIRED = [
    EditorialStatus.WATCHLIST,
    EditorialStatus.EDITORIAL_REVIEW,
    EditorialStatus.READY_FOR_APPROVAL,
    EditorialStatus.APPROVED,
    EditorialStatus.PUBLISHED,
]


def test_candidate_event_may_start_without_audience():
    event = make_event(audience=())
    assert event.editorial_status is EditorialStatus.CANDIDATE
    assert event.audience == ()


def test_candidate_without_audience_can_be_rejected_with_no_audience():
    event = make_event(audience=())
    rejected = dataclasses.replace(
        event, editorial_status=EditorialStatus.REJECT, status_reason="no_audience"
    )
    assert rejected.status_reason == "no_audience"


def test_archived_event_may_have_no_audience():
    event = make_event(audience=(), editorial_status=EditorialStatus.ARCHIVED)
    assert event.audience == ()


@pytest.mark.parametrize("status", AUDIENCE_REQUIRED)
def test_editorial_progression_requires_audience(status):
    with pytest.raises(DomainValidationError):
        make_event(audience=(), editorial_status=status)
    assert make_event(editorial_status=status).audience == ("beneficiarios_prestacoes",)


@pytest.mark.parametrize("status", AUDIENCE_REQUIRED)
def test_candidate_without_audience_cannot_advance(status):
    event = make_event(audience=())
    with pytest.raises(DomainValidationError):
        dataclasses.replace(event, editorial_status=status)


# --- DEC-020: legal_stage --------------------------------------------------


@pytest.mark.parametrize(
    "verification",
    [
        VerificationStatus.UNVERIFIED,
        VerificationStatus.VERIFIED_EDITORIAL,
        VerificationStatus.CONTRADICTED,
    ],
)
@pytest.mark.parametrize("stage", list(LegalStage))
def test_proposed_stage_is_not_officially_confirmed(verification, stage):
    event = make_event(legal_stage=stage, verification_status=verification)
    assert event.legal_stage is stage
    assert event.legal_stage_officially_confirmed is False


def test_new_event_stage_is_never_officially_confirmed():
    assert make_event(legal_stage=LegalStage.IN_FORCE).legal_stage_officially_confirmed is False


@pytest.mark.parametrize("stage", [s for s in LegalStage if s is not LegalStage.NOT_APPLICABLE])
def test_stage_is_officially_confirmed_only_when_event_is_verified_official(stage):
    event = make_event(legal_stage=stage, verification_status=VerificationStatus.VERIFIED_OFFICIAL)
    assert event.legal_stage_officially_confirmed is True


def test_not_applicable_stage_has_nothing_to_confirm():
    event = make_event(
        legal_stage=LegalStage.NOT_APPLICABLE,
        verification_status=VerificationStatus.VERIFIED_OFFICIAL,
    )
    assert event.legal_stage_officially_confirmed is False
