"""Regras de elegibilidade e formatação de mensagens WhatsApp (DEC-048)."""

from dataclasses import dataclass
from math import isfinite
from unicodedata import category
from urllib.parse import urlsplit

from tensdireito_content_engine.domain.enums import EditorialStatus, VerificationStatus
from tensdireito_content_engine.domain.validation import require_text

MINIMUM_RELEVANCE_SCORE = 65.0
ELIGIBLE_VERIFICATION_STATUSES = frozenset(
    {VerificationStatus.VERIFIED_EDITORIAL, VerificationStatus.VERIFIED_OFFICIAL}
)


@dataclass(frozen=True, slots=True, kw_only=True)
class WhatsAppMessage:
    """Conteúdo editorial estruturado para uma mensagem WhatsApp."""

    emoji: str
    title: str
    key_points: tuple[str, ...]
    cta: str
    url: str

    def __post_init__(self) -> None:
        for field in ("emoji", "title", "cta", "url"):
            require_text(getattr(self, field), field)
            if "\n" in getattr(self, field) or "\r" in getattr(self, field):
                raise ValueError(f"{field} tem de ocupar uma única linha")

        if not any(category(character).startswith("S") for character in self.emoji):
            raise ValueError("emoji tem de conter pelo menos um símbolo")
        if not isinstance(self.key_points, tuple) or not 2 <= len(self.key_points) <= 3:
            raise ValueError("key_points tem de conter 2 ou 3 pontos")
        for point in self.key_points:
            require_text(point, "key_points")
            if "\n" in point or "\r" in point:
                raise ValueError("cada key_point tem de ocupar uma única linha")

        parsed_url = urlsplit(self.url)
        if parsed_url.scheme != "https" or not parsed_url.hostname:
            raise ValueError("url tem de ser uma hiperligação HTTPS absoluta")
        if parsed_url.username is not None or parsed_url.password is not None:
            raise ValueError("url não pode conter credenciais")


def check_whatsapp_eligibility(
    editorial_score: int | float,
    verification_status: VerificationStatus,
    editorial_status: EditorialStatus,
    is_duplicate: bool,
) -> tuple[str, ...]:
    """Devolve os motivos que impedem a publicação; vazio significa elegível."""
    if (
        isinstance(editorial_score, bool)
        or not isinstance(editorial_score, int | float)
        or not isfinite(editorial_score)
        or not 0 <= editorial_score <= 100
    ):
        raise ValueError("editorial_score tem de ser um número finito entre 0 e 100")
    if not isinstance(verification_status, VerificationStatus):
        raise ValueError("verification_status inválido")
    if not isinstance(editorial_status, EditorialStatus):
        raise ValueError("editorial_status inválido")
    if not isinstance(is_duplicate, bool):
        raise ValueError("is_duplicate tem de ser booleano")

    reasons: list[str] = []
    if editorial_score < MINIMUM_RELEVANCE_SCORE:
        reasons.append(f"score de relevância inferior a {MINIMUM_RELEVANCE_SCORE:g}")
    if verification_status not in ELIGIBLE_VERIFICATION_STATUSES:
        reasons.append("item não validado editorialmente ou oficialmente")
    if editorial_status is not EditorialStatus.APPROVED:
        reasons.append("item sem aprovação humana")
    if is_duplicate:
        reasons.append("item duplicado")
    return tuple(reasons)


def format_whatsapp_message(message: WhatsAppMessage) -> str:
    """Formata título, pontos-chave, CTA e hiperligação com sintaxe WhatsApp."""
    points = "\n".join(f"• {point}" for point in message.key_points)
    return (
        f"{message.emoji} *{message.title}*\n\n"
        f"{points}\n\n"
        f"👉 *{message.cta}*\n"
        f"_Saiba mais:_ {message.url}"
    )
