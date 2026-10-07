"""Normalização mecânica de texto (DEC-021).

Só transformações que não alteram o significado: forma Unicode NFC, quebras de linha,
espaços. Não resume, não traduz, não corrige, não muda maiúsculas/minúsculas, não
remove marcação nem pontuação. Funções puras e determinísticas.
"""

import re
import unicodedata

# Espaço em branco horizontal: qualquer espaço Unicode (inclui tabulação e NBSP),
# excepto a quebra de linha.
_HORIZONTAL_SPACE = re.compile(r"[^\S\n]+")
_LINE_BREAK = re.compile(r"\r\n|\r")
_BLANK_LINES = re.compile(r"\n{3,}")
_ANY_SPACE = re.compile(r"\s+")


def _require_str(value: object) -> str:
    if not isinstance(value, str):
        raise TypeError(f"esperado str, recebido {type(value).__name__}")
    return value


def normalize_text(value: str) -> str:
    """Normaliza um texto de várias linhas, preservando parágrafos.

    1. Unicode NFC (equivalência canónica; ex.: "a" + til combinante → "ã").
    2. Quebras de linha `\\r\\n` e `\\r` → `\\n`.
    3. Espaço horizontal consecutivo → um espaço; sem espaços no início/fim das linhas.
    4. Três ou mais quebras seguidas → uma linha em branco (separador de parágrafo).
    5. Sem espaço em branco no início/fim do texto.
    """
    text = unicodedata.normalize("NFC", _require_str(value))
    text = _LINE_BREAK.sub("\n", text)
    lines = (_HORIZONTAL_SPACE.sub(" ", line).strip() for line in text.split("\n"))
    text = "\n".join(lines)
    return _BLANK_LINES.sub("\n\n", text).strip()


def normalize_title(value: str) -> str:
    """Normaliza um título numa única linha: NFC e qualquer espaço consecutivo → um espaço."""
    title = unicodedata.normalize("NFC", _require_str(value))
    return _ANY_SPACE.sub(" ", title).strip()
