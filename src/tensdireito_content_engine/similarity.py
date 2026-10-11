"""Semelhança lexical de títulos para agrupar notícias do mesmo tema (DEC-059).

Sem IA (AI_RULES.md §2, `same_event` substituível por similaridade lexical): dois
títulos são do mesmo tema quando a sobreposição das palavras significativas
(coeficiente de Jaccard) é ≥ 0,5 com pelo menos três palavras em comum, ou ≥ 0,3
com pelo menos quatro (títulos longos sobre o mesmo acontecimento).
"""

import re

from tensdireito_content_engine.topics import fold

# (palavras em comum, Jaccard mínimo): basta cumprir uma das regras.
_RULES = ((3, 0.5), (4, 0.3))

_WORD = re.compile(r"\w+")
_STOPWORDS = frozenset(
    """
    a o as os um uma uns umas de do da dos das em no na nos nas ao aos à às por pelo pela
    pelos pelas para com sem sob sobre entre e ou mas que se ja nao sim mais menos muito
    muita muitos muitas como quando onde quem qual quais este esta estes estas esse essa
    isso isto aquele aquela seu sua seus suas ser sao foi vai vao tem ter ha hoje ate
    saiba veja agora novo nova novos novas portugal portugueses
    """.split()
)


def title_words(title: str) -> frozenset[str]:
    """Palavras significativas do título, sem diacríticos nem palavras vazias."""
    return frozenset(
        word
        for word in _WORD.findall(fold(title))
        if word not in _STOPWORDS and (len(word) >= 3 or word.isdigit())
    )


def same_topic(first: str, second: str) -> bool:
    """`True` se os dois títulos tratam, lexicalmente, o mesmo tema."""
    a, b = title_words(first), title_words(second)
    if not a or not b:
        return False
    shared = len(a & b)
    jaccard = shared / len(a | b)
    return any(shared >= words and jaccard >= minimum for words, minimum in _RULES)
