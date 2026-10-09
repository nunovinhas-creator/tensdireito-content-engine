from datetime import UTC, datetime

from tensdireito_content_engine.domain import RawItem
from tensdireito_content_engine.normalize import normalize_raw_item
from tensdireito_content_engine.scoring import score_item


def test_initial_score_is_deterministic_and_does_not_claim_verification():
    item = RawItem(
        url="https://example.org",
        title="Nova prestação aumenta para trabalhadores; prazo para pedir apoio",
        raw_content=(
            "<item><description>A nova prestação aumenta e cria direito para trabalhadores. "
            "Deve requerer apoio até 31 de outubro.</description></item>"
        ),
        fetched_at=datetime(2026, 10, 9, tzinfo=UTC),
    )
    normalized = normalize_raw_item(item)

    first = score_item(normalized)

    assert first == score_item(normalized)
    assert first.value == 74
    assert dict(first.components) == {
        "impact": 5,
        "reach": 3,
        "actionability": 5,
        "urgency": 4,
        "novelty": 0,
        "interest": 0,
    }
    assert not hasattr(first, "verification_status")


def test_unrelated_text_scores_below_draft_threshold():
    item = RawItem(
        url="https://example.org",
        title="Nota local",
        raw_content="<item><description>Notas de cultura local.</description></item>",
        fetched_at=datetime(2026, 10, 9, tzinfo=UTC),
    )

    assert score_item(normalize_raw_item(item)).value < 65
