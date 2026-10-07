from tensdireito_content_engine.domain import (
    EditorialStatus,
    ImpactType,
    LegalStage,
    VerificationStatus,
)


def test_verification_status_values_follow_dec_003():
    assert [s.name for s in VerificationStatus] == [
        "UNVERIFIED",
        "VERIFIED_EDITORIAL",
        "VERIFIED_OFFICIAL",
        "CONTRADICTED",
    ]


def test_stored_values_are_lowercase_names():
    for enum_type in (VerificationStatus, LegalStage, ImpactType, EditorialStatus):
        for member in enum_type:
            assert member.value == member.name.lower()


def test_verified_official_and_editorial_are_distinct():
    assert VerificationStatus.VERIFIED_OFFICIAL != VerificationStatus.VERIFIED_EDITORIAL


def test_legal_stage_values_follow_data_model():
    assert {s.value for s in LegalStage} == {
        "not_applicable",
        "proposal",
        "announcement",
        "approved",
        "published",
        "in_force",
        "ended",
    }


def test_impact_type_values_follow_editorial_policy():
    assert len(ImpactType) == 11
    assert ImpactType.AMOUNT_CHANGE.value == "amount_change"


def test_verification_legal_stage_and_impact_are_separate_vocabularies():
    verification = {s.value for s in VerificationStatus}
    legal = {s.value for s in LegalStage}
    impact = {s.value for s in ImpactType}
    assert verification.isdisjoint(legal)
    assert verification.isdisjoint(impact)
    assert legal.isdisjoint(impact)
