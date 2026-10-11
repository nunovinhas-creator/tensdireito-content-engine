import pytest

from tensdireito_content_engine.domain.enums import EditorialStatus, VerificationStatus
from tensdireito_content_engine.publish.whatsapp import (
    MINIMUM_RELEVANCE_SCORE,
    WhatsAppMessage,
    check_whatsapp_eligibility,
    format_whatsapp_message,
)


def create_message(**overrides):
    values = {
        "emoji": "📢",
        "title": "Novo apoio às famílias",
        "key_points": ("Pode pedir online", "O prazo termina em junho"),
        "cta": "Veja se tem direito",
        "url": "https://example.org/direito",
    }
    return WhatsAppMessage(**(values | overrides))


def test_format_whatsapp_message_uses_channel_syntax_and_required_structure():
    assert format_whatsapp_message(create_message()) == (
        "📢 **NOVO APOIO ÀS FAMÍLIAS**\n\n"
        "👉 Pode pedir online\n"
        "👉 O prazo termina em junho\n\n"
        "🔎 **Veja se tem direito:** https://example.org/direito\n\n"
        "👉 **Tensdireito.com — informação útil para o seu bolso.**"
    )


@pytest.mark.parametrize("number_of_points", [1, 4])
def test_message_requires_two_or_three_key_points(number_of_points):
    with pytest.raises(ValueError, match="2 ou 3 pontos"):
        create_message(key_points=tuple(f"Ponto {index}" for index in range(number_of_points)))


def test_message_requires_emoji_and_absolute_https_link():
    with pytest.raises(ValueError, match="símbolo"):
        create_message(emoji="Aviso")
    with pytest.raises(ValueError, match="HTTPS absoluta"):
        create_message(url="http://example.org/direito")


def test_eligibility_accepts_minimum_score_verified_and_approved_non_duplicate():
    assert (
        check_whatsapp_eligibility(
            MINIMUM_RELEVANCE_SCORE,
            VerificationStatus.VERIFIED_OFFICIAL,
            EditorialStatus.APPROVED,
            False,
        )
        == ()
    )


@pytest.mark.parametrize(
    ("score", "verification", "editorial", "duplicate", "expected_reason"),
    [
        (
            64.99,
            VerificationStatus.VERIFIED_OFFICIAL,
            EditorialStatus.APPROVED,
            False,
            "score de relevância",
        ),
        (
            80,
            VerificationStatus.UNVERIFIED,
            EditorialStatus.APPROVED,
            False,
            "não validado",
        ),
        (
            80,
            VerificationStatus.VERIFIED_EDITORIAL,
            EditorialStatus.READY_FOR_APPROVAL,
            False,
            "sem aprovação humana",
        ),
        (
            80,
            VerificationStatus.VERIFIED_EDITORIAL,
            EditorialStatus.APPROVED,
            True,
            "duplicado",
        ),
    ],
)
def test_eligibility_reports_each_blocking_criterion(
    score, verification, editorial, duplicate, expected_reason
):
    reasons = check_whatsapp_eligibility(score, verification, editorial, duplicate)
    assert len(reasons) == 1
    assert expected_reason in reasons[0]


@pytest.mark.parametrize("score", [-1, 101, float("nan"), True])
def test_eligibility_rejects_invalid_scores(score):
    with pytest.raises(ValueError, match="número finito entre 0 e 100"):
        check_whatsapp_eligibility(
            score,
            VerificationStatus.VERIFIED_OFFICIAL,
            EditorialStatus.APPROVED,
            False,
        )
