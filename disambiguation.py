"""
disambiguation.py — resolve menções ambíguas (aliases/sobrenomes
compartilhados por mais de um político monitorado) usando o contexto
ao redor da menção no texto.

O problema: com sobrenomes curtos habilitados como alias (ver
camara_api.py e senado_api.py), é comum que mais de um político
monitorado compartilhe o mesmo sobrenome — o caso real que motivou
este módulo é "Bolsonaro", que hoje corresponde tanto a Jair Bolsonaro
(ex-presidente) quanto a Flávio Bolsonaro (senador pelo RJ).

A solução: quando uma menção casa com mais de um político, olhamos
para uma janela de texto ao redor da menção (a mesma frase,
tipicamente) procurando pistas — palavras do cargo ("senador",
"deputado", "ex-presidente", "ministro", "governador") e a UF
mencionada perto do nome (ex.: "(RJ)"). O partido (sigla) NÃO é usado
como pista por padrão, porque é comum político da mesma família estar
no mesmo partido (como no caso Bolsonaro/Bolsonaro), o que tornaria a
pista inútil ou até enganosa nesses casos.

Em caso de empate ou nenhuma pista encontrada, a função não resolve
(retorna None) — o princípio aqui é priorizar precisão sobre
cobertura: melhor deixar uma menção ambígua sem commit do que atribuí-
la ao político errado.
"""

import re

from text_utils import normalize

# Palavras de cargo reconhecidas como pista de contexto, mapeadas para
# os termos que costumam aparecer no campo "role" de config.py.
_ROLE_KEYWORDS = [
    "presidente",
    "ex-presidente",
    "deputado",
    "deputada",
    "senador",
    "senadora",
    "ministro",
    "ministra",
    "governador",
    "governadora",
]

_UF_PATTERN = re.compile(r"\(([A-Z]{2})\)")


def _role_keywords_in(text_norm: str) -> set[str]:
    return {kw for kw in _ROLE_KEYWORDS if kw in text_norm}


def _role_keywords_of_politician(politician: dict) -> set[str]:
    role_norm = normalize(politician.get("role", ""))
    return _role_keywords_in(role_norm)


def _uf_of_politician(politician: dict) -> str | None:
    match = _UF_PATTERN.search(politician.get("role", ""))
    return match.group(1) if match else None


def score_context(politician: dict, context_text: str) -> int:
    """
    Pontua o quanto o contexto ao redor da menção "combina" com este
    político. Quanto maior, mais provável que a menção seja sobre ele.
    """
    context_norm = normalize(context_text)
    score = 0

    context_role_keywords = _role_keywords_in(context_norm)
    politician_role_keywords = _role_keywords_of_politician(politician)
    if context_role_keywords & politician_role_keywords:
        score += 1

    uf = _uf_of_politician(politician)
    if uf:
        # UF perto do nome no texto original (ex: "senadora por SP"),
        # checado como token maiúsculo isolado para reduzir ruído.
        uf_pattern = re.compile(rf"(?<![A-Za-zÀ-ÿ]){uf}(?![A-Za-zÀ-ÿ])")
        if uf_pattern.search(context_text):
            score += 1

    return score


def resolve_ambiguous_mention(
    candidates: list[dict], context_text: str
) -> dict | None:
    """
    Recebe uma lista de políticos que casaram com a mesma menção
    (ambígua) e o texto de contexto ao redor dela. Retorna o político
    mais provável, ou None se não for possível decidir com confiança
    (nenhuma pista, ou pistas empatadas entre dois ou mais candidatos).
    """
    if len(candidates) == 1:
        return candidates[0]

    scored = [(score_context(p, context_text), p) for p in candidates]
    scored.sort(key=lambda pair: pair[0], reverse=True)

    best_score, best_politician = scored[0]
    if best_score == 0:
        return None  # nenhuma pista — não arrisca

    # Se houver empate no topo, também não arrisca.
    tied = [p for score, p in scored if score == best_score]
    if len(tied) > 1:
        return None

    return best_politician


if __name__ == "__main__":
    jair = {
        "slug": "jair-bolsonaro",
        "name": "Jair Bolsonaro",
        "role": "Ex-Presidente",
        "party": "PL",
    }
    flavio = {
        "slug": "flavio-bolsonaro",
        "name": "Flávio Bolsonaro",
        "role": "Senador(a) (RJ)",
        "party": "PL",
    }
    candidates = [jair, flavio]

    cases = [
        "O ex-presidente Bolsonaro comentou o julgamento em entrevista",
        "O senador Bolsonaro criticou a proposta em discurso no plenário",
        "A senadora por RJ, Bolsonaro, defendeu o projeto",
        "Bolsonaro se reuniu com aliados nesta tarde",  # sem pista -> None
    ]
    for text in cases:
        resolved = resolve_ambiguous_mention(candidates, text)
        slug = resolved["slug"] if resolved else None
        print(f"{text!r} -> {slug}")
