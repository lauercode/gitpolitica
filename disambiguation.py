"""
disambiguation.py — resolve menções ambíguas (aliases/sobrenomes
compartilhados por mais de um político monitorado) usando o contexto
ao redor da menção no texto, e descarta menções de sobrenome que na
verdade pertencem a uma pessoa NÃO monitorada.

Dois problemas relacionados, resolvidos aqui:

1. AMBIGUIDADE ENTRE POLÍTICOS MONITORADOS: com sobrenomes curtos
   habilitados como alias (ver camara_api.py e senado_api.py), é comum
   que mais de um político monitorado compartilhe o mesmo sobrenome —
   o caso que motivou esse mecanismo é "Bolsonaro", que corresponde
   tanto a Jair Bolsonaro (ex-presidente) quanto a Flávio Bolsonaro
   (senador pelo RJ). Resolvido por score_context()/resolve_ambiguous_mention(),
   usando pistas de cargo e UF no texto ao redor da menção.

2. SOBRENOME DE UMA PESSOA NÃO MONITORADA: um problema mais sério,
   encontrado com dados reais em produção — a notícia "Confira a
   agenda dos candidatos à Presidência" cita "Edmilson Costa (PCB)",
   um candidato presidencial que NÃO tem nada a ver com Humberto Costa
   (senador monitorado), mas como "Costa" é alias dele, o sistema
   atribuiu a menção errada. Isso acontece mesmo sem ambiguidade entre
   políticos monitorados (só existe 1 "Costa" na nossa lista) — o
   problema é a palavra bater com o sobrenome de uma pessoa qualquer.

   A defesa: check_preceding_name() olha a palavra imediatamente
   ANTES da menção. Se houver um nome capitalizado ali (formando um
   nome completo tipo "Edmilson Costa") que não é o primeiro nome de
   nenhum dos candidatos monitorados que compartilham esse alias, a
   menção é descartada — é sobrenome de outra pessoa. Se o nome
   anterior bater com o primeiro nome de UM dos candidatos, isso na
   verdade é um sinal forte e resolve a ambiguidade direto pra ele
   (por exemplo, "Jair Bolsonaro" perto de "Flávio Bolsonaro" no mesmo
   texto: cada ocorrência de "Bolsonaro" é resolvida individualmente
   pelo nome que a precede).

Em qualquer caso de dúvida (nenhuma pista, pistas empatadas, ou nome
anterior que não bate com ninguém monitorado), a função não resolve
(retorna None) — o princípio aqui é sempre priorizar precisão sobre
cobertura: melhor deixar uma menção sem commit do que atribuí-la à
pessoa errada.
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
_PRECEDING_NAME_PATTERN = re.compile(r"([A-ZÀ-Ý][a-zà-ÿ]+)\s*$")


def _role_keywords_in(text_norm: str) -> set[str]:
    return {kw for kw in _ROLE_KEYWORDS if kw in text_norm}


def _role_keywords_of_politician(politician: dict) -> set[str]:
    role_norm = normalize(politician.get("role", ""))
    return _role_keywords_in(role_norm)


def _uf_of_politician(politician: dict) -> str | None:
    match = _UF_PATTERN.search(politician.get("role", ""))
    return match.group(1) if match else None


def _non_surname_tokens_of(politician: dict) -> set[str]:
    """
    Todos os tokens do nome, exceto o último (sobrenome) — não só o
    primeiro. Bug real encontrado em produção: para nomes de urna no
    padrão "Profissão + Nome + Sobrenome" (ex.: "Escritor Augusto
    Cury"), usar só o primeiro token ("Escritor") pra comparar contra
    a palavra que precede uma menção de "Cury" faz o sistema descartar
    "Augusto Cury" por engano — "Augusto" não bate com "Escritor", mas
    bate perfeitamente com o segundo token do nome de verdade da
    pessoa. Checar o conjunto inteiro (exceto o sobrenome) resolve
    isso sem precisar reconhecer "Escritor" como título/profissão
    numa lista fixa — funciona pra qualquer padrão parecido.
    """
    result: set[str] = set()
    # Também considera os aliases de nome completo (ex.: nome de urna
    # "Zema" tem nome civil "Romeu Zema Neto" — "Romeu" precisa contar
    # como parte do nome dele, senão "Romeu Zema" era descartado).
    for full in [politician["name"], *politician.get("aliases", [])]:
        tokens = full.strip().split()
        if len(tokens) > 1:
            result.update(normalize(t) for t in tokens[:-1])
    return result


def check_preceding_name(
    text: str, match_start: int, candidates: list[dict]
) -> tuple[bool, dict | None]:
    """
    Olha a palavra capitalizada imediatamente antes de match_start (se
    houver). Retorna (deve_descartar, resolvido_diretamente):

    - Sem palavra capitalizada antes (ou início do texto): (False, None)
      — nada a decidir aqui, segue para as outras checagens.
    - Palavra anterior bate com algum token do nome (exceto o
      sobrenome) de exatamente 1 candidato: (False, esse_candidato) —
      resolve direto, sinal forte.
    - Palavra anterior bate com o nome de 2+ candidatos (raro):
      (False, None) — ainda ambíguo, segue para outras checagens.
    - Palavra anterior NÃO bate com o nome de nenhum candidato:
      (True, None) — descarta, é sobrenome de outra pessoa.
    """
    preceding_match = _PRECEDING_NAME_PATTERN.search(text[:match_start])
    if not preceding_match:
        return False, None

    preceding_norm = normalize(preceding_match.group(1))
    matching = [p for p in candidates if preceding_norm in _non_surname_tokens_of(p)]

    if len(matching) == 1:
        return False, matching[0]
    if len(matching) == 0:
        return True, None
    return False, None  # 2+ bateram (raríssimo) — deixa pras outras checagens


# --- Co-menção de pares do mesmo cargo -------------------------------
#
# Caso real que motivou isso: dois candidatos monitorados genuinamente
# compartilham o sobrenome "Cury" — "Escritor Augusto Cury" (candidato
# a Presidente) e "João Cury" (outro cargo). Manchetes como "Quaest, 1º
# turno: Lula, 39%; Flávio Bolsonaro, 34%; Caiado, 4%; Cury, 4%;
# Zema, 1%" não têm nenhuma palavra de cargo/UF explícita, mas um leitor
# humano sabe na hora qual "Cury" é — o que está sendo listado ao lado
# de OUTROS candidatos a Presidente. Esse sinal usa isso: se o contexto
# também cita alguém do MESMO cargo que o candidato sendo avaliado, é
# evidência de que o texto é sobre esse grupo de cargo.

from config import POLITICIANS
from text_utils import extract_cargo_category

_NAME_LIKE_PATTERN = re.compile(r"[A-ZÀ-Ý][a-zà-ÿ]+(?:\s+[A-ZÀ-Ý][a-zà-ÿ]+){0,3}")

# cargo -> conjunto de todos os aliases (normalizados) de TODOS os
# políticos desse cargo. Conjunto "achatado" de propósito: aqui só
# importa saber SE alguém do mesmo cargo é citado, não QUEM — e
# lookup em conjunto é O(1), ao contrário de varrer milhares de nomes
# (o cargo "Deputado Estadual" tem milhares de pessoas).
_ALIASES_BY_CARGO: dict[str, set[str]] = {}
for _p in POLITICIANS:
    _cargo = extract_cargo_category(_p.get("candidacy_role") or _p.get("role", ""))
    _names = {normalize(a) for a in _p.get("aliases", [])} | {normalize(_p["name"])}
    _ALIASES_BY_CARGO.setdefault(_cargo, set()).update(_names)


def _peer_comention_bonus(politician: dict, context_text: str) -> int:
    """
    +1 se o contexto também menciona (por alias) OUTRO político do
    mesmo cargo que `politician` — e não é o próprio nome dele.
    """
    # Cargo da CANDIDATURA em 2026, se houver (um senador que concorre a
    # Presidente é par dos candidatos a Presidente numa pesquisa).
    cargo = extract_cargo_category(politician.get("candidacy_role") or politician.get("role", ""))
    peer_aliases = _ALIASES_BY_CARGO.get(cargo)
    if not peer_aliases:
        return 0

    own_aliases = {normalize(a) for a in politician.get("aliases", [])} | {
        normalize(politician["name"])
    }

    for match in _NAME_LIKE_PATTERN.finditer(context_text):
        candidate = normalize(match.group(0))
        # Ignora o próprio candidato (e o alias ambíguo em disputa).
        if candidate in own_aliases:
            continue
        if candidate in peer_aliases:
            return 1
    return 0


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

    score += _peer_comention_bonus(politician, context_text)

    return score


def resolve_ambiguous_mention(
    candidates: list[dict], context_text: str
) -> dict | None:
    """
    Recebe uma lista de políticos que casaram com a mesma menção
    (ambígua) e o texto de contexto ao redor dela. Retorna o político
    mais provável, ou None se não for possível decidir com confiança
    (nenhuma pista, ou pistas empatadas entre dois ou mais candidatos).

    Não faz a checagem de nome precedente — isso é responsabilidade de
    resolve_mention(), que chama esta função só como uma das etapas.
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


def resolve_mention(
    candidates: list[dict], text: str, match_start: int, context_text: str
) -> dict | None:
    """
    Ponto de entrada único usado por matcher.py: combina a checagem de
    nome precedente (prioridade máxima — pode descartar mesmo com 1
    candidato só) com a desambiguação por cargo/UF.
    """
    should_discard, resolved_directly = check_preceding_name(text, match_start, candidates)
    if should_discard:
        return None
    if resolved_directly:
        return resolved_directly

    return resolve_ambiguous_mention(candidates, context_text)


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
    humberto_costa = {
        "slug": "humberto-costa",
        "name": "Humberto Costa",
        "role": "Senador(a) (PE)",
        "party": "PT",
    }

    print("--- Ambiguidade entre políticos monitorados (Bolsonaro/Bolsonaro) ---")
    candidates = [jair, flavio]
    cases = [
        "O ex-presidente Bolsonaro comentou o julgamento em entrevista",
        "O senador Bolsonaro criticou a proposta em discurso no plenário",
        "Bolsonaro se reuniu com aliados nesta tarde",  # sem pista -> None
        "Jair Bolsonaro e Flávio Bolsonaro discutiram nos bastidores",
    ]
    for text in cases:
        for match in re.finditer(r"Bolsonaro", text):
            context = text[max(0, match.start() - 80): match.end() + 80]
            resolved = resolve_mention(candidates, text, match.start(), context)
            slug = resolved["slug"] if resolved else None
            print(f"{text!r} [pos {match.start()}] -> {slug}")

    print("\n--- Sobrenome de pessoa não monitorada (Costa/Costa) ---")
    candidates = [humberto_costa]
    cases = [
        "Humberto Costa vota a favor do projeto de lei",
        "Costa vota a favor do projeto de lei",  # sem nome antes -> ok
        "Edmilson Costa (PCB) participa de entrevista",  # pessoa diferente -> None
    ]
    for text in cases:
        match = re.search(r"Costa", text)
        context = text[max(0, match.start() - 80): match.end() + 80]
        resolved = resolve_mention(candidates, text, match.start(), context)
        slug = resolved["slug"] if resolved else None
        print(f"{text!r} -> {slug}")
