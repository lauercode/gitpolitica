"""
matcher.py — identifica quais políticos monitorados são citados
em uma notícia (título + resumo).

Três camadas, combinadas por padrão:

1. EXATA (find_mentioned_exact): casamento direto por alias, rápido e
   sem falsos positivos. Só existe quando o texto usa exatamente uma
   das variações de nome já cadastradas em config.py.

2. FUZZY (find_mentioned_fuzzy): um "NER leve" sem dependências
   externas. Primeiro extrai candidatos a nome próprio do texto
   (sequências de 1-4 palavras capitalizadas, com conectores como
   "de"/"da"/"dos"), depois compara cada candidato contra os nomes e
   aliases conhecidos usando difflib (similaridade de string), após
   normalizar acentuação. Isso pega variações que a camada exata
   perderia — erros de digitação, nomes sem acento, abreviações
   próximas — sem precisar listar manualmente cada variação.

3. DESAMBIGUAÇÃO (disambiguation.py): tanto a camada exata quanto a
   fuzzy podem encontrar mais de um político para a mesma menção — por
   exemplo, "Bolsonaro" corresponde tanto a Jair Bolsonaro quanto a
   Flávio Bolsonaro, já que ambos têm esse sobrenome cadastrado como
   alias (veja camara_api.py/senado_api.py, que adicionam o sobrenome
   automaticamente). Quando isso acontece, olhamos para o texto ao
   redor da menção em busca de pistas de cargo/UF para decidir. Sem
   pista clara, a menção é descartada (precisão > cobertura).

find_mentioned_politicians() combina as três camadas e é o que o resto
do pipeline usa.

Evolução futura (veja ner_spacy.py): trocar/complementar a extração de
candidatos por NER de verdade via spaCy, que reconhece nomes de pessoas
mesmo sem estarem pré-cadastrados — útil para descobrir menções a
políticos ainda não monitorados.
"""

import re
import difflib
from config import POLITICIANS
from text_utils import normalize
from disambiguation import resolve_ambiguous_mention

_CONTEXT_RADIUS = 80  # caracteres de contexto para cada lado da menção


def _context_window(text: str, start: int, end: int) -> str:
    return text[max(0, start - _CONTEXT_RADIUS): end + _CONTEXT_RADIUS]


def _resolve(candidates: list[dict], context_text: str) -> dict | None:
    """Atalho: 1 candidato -> direto; 2+ -> desambigua por contexto."""
    if len(candidates) == 1:
        return candidates[0]
    return resolve_ambiguous_mention(candidates, context_text)


# --- Camada 1: casamento exato por alias ------------------------------
#
# Indexado pelo texto cru do alias (não normalizado), porque o que nos
# interessa aqui é: duas entradas de POLITICIANS que compartilham
# literalmente a mesma string de alias (ex: "Bolsonaro") formam um
# grupo ambíguo que precisa de contexto para ser resolvido.

def _build_alias_index() -> dict[str, list[dict]]:
    index: dict[str, list[dict]] = {}
    for politician in POLITICIANS:
        for alias in politician["aliases"]:
            index.setdefault(alias, []).append(politician)
    return index


_ALIAS_INDEX = _build_alias_index()
_ALIAS_PATTERNS = {
    alias: re.compile(rf"(?<![A-Za-zÀ-ÿ]){re.escape(alias)}(?![A-Za-zÀ-ÿ])", re.IGNORECASE)
    for alias in _ALIAS_INDEX
}


def find_mentioned_exact(text: str) -> list[dict]:
    """Casamento exato por alias, com desambiguação por contexto quando necessário."""
    mentioned = {}
    for alias, candidates in _ALIAS_INDEX.items():
        for match in _ALIAS_PATTERNS[alias].finditer(text):
            resolved = _resolve(candidates, _context_window(text, match.start(), match.end()))
            if resolved:
                mentioned[resolved["slug"]] = resolved
    return list(mentioned.values())


# --- Camada 2: extração de candidatos + fuzzy matching -----------------

_NAME_TOKEN = r"[A-ZÀ-Ý][a-zà-ÿ]+"
_CONNECTOR = r"(?:de|da|do|dos|das)"
_CANDIDATE_PATTERN = re.compile(
    rf"{_NAME_TOKEN}(?:\s+(?:{_CONNECTOR}\s+)?{_NAME_TOKEN}){{0,3}}"
)

# Limiares de similaridade (0-1). Candidatos de uma palavra só exigem
# similaridade mais alta, para reduzir o risco de falso positivo com
# palavras comuns capitalizadas em início de frase.
_THRESHOLD_MULTI_WORD = 0.85
_THRESHOLD_SINGLE_WORD = 0.90
_TIE_EPSILON = 0.001  # diferença de score considerada "empate"


def extract_candidate_names(text: str) -> list[str]:
    """Extrai sequências de palavras capitalizadas que podem ser nomes próprios."""
    return _CANDIDATE_PATTERN.findall(text)


def _best_ratio(candidate_norm: str, targets: list[str]) -> float:
    best = 0.0
    for target in targets:
        ratio = difflib.SequenceMatcher(None, candidate_norm, normalize(target)).ratio()
        best = max(best, ratio)
    return best


def find_mentioned_fuzzy(text: str) -> list[dict]:
    """
    Extrai candidatos a nome do texto e casa por similaridade contra os
    políticos conhecidos. Candidatos de uma palavra só são comparados
    contra os aliases (curados/gerados) para evitar comparar contra um
    nome completo de duas palavras e gerar falso positivo com
    sobrenomes ambíguos. Quando o candidato empata entre dois ou mais
    políticos, usa o contexto ao redor para decidir (ou descarta).
    """
    mentioned = {}

    for match in _CANDIDATE_PATTERN.finditer(text):
        candidate = match.group(0)
        candidate_norm = normalize(candidate)
        is_single_word = " " not in candidate_norm
        threshold = _THRESHOLD_SINGLE_WORD if is_single_word else _THRESHOLD_MULTI_WORD

        scores = []
        for politician in POLITICIANS:
            targets = politician["aliases"] if is_single_word else (
                [politician["name"]] + politician["aliases"]
            )
            score = _best_ratio(candidate_norm, targets)
            scores.append((score, politician))

        if not scores:
            continue

        best_score = max(score for score, _ in scores)
        if best_score < threshold:
            continue

        tied_candidates = [p for score, p in scores if score >= best_score - _TIE_EPSILON]
        resolved = _resolve(
            tied_candidates, _context_window(text, match.start(), match.end())
        )
        if resolved:
            mentioned[resolved["slug"]] = resolved

    return list(mentioned.values())


# --- Combinação ---------------------------------------------------------

def find_mentioned_politicians(text: str) -> list[dict]:
    """Combina casamento exato + fuzzy, deduplicado por slug."""
    combined = {}
    for politician in find_mentioned_exact(text):
        combined[politician["slug"]] = politician
    for politician in find_mentioned_fuzzy(text):
        combined[politician["slug"]] = politician
    return list(combined.values())


if __name__ == "__main__":
    samples = [
        # casamento exato, deve continuar funcionando
        "Lula sanciona nova lei durante cerimônia no Planalto",
        "Arthur Lira articula pauta do Congresso para o segundo semestre",
        "Tarcísio de Freitas anuncia pacote de investimentos em SP",
        "Notícia sem nenhum político conhecido",
        # variações que só a camada fuzzy deveria pegar
        "Artur Lira articula pauta do Congresso",              # erro de digitação
        "Tarcisio Freitas anuncia pacote de investimentos",     # sem acento, sem 'de'
        "Bia Kikis participa de comissão na Câmara",            # typo no sobrenome
        # possíveis falsos positivos que NÃO deveriam casar com ninguém
        "Congresso Nacional aprova nova lei orçamentária",
        "Governo Federal libera novos recursos para saúde",
        "Estados Unidos anunciam nova tarifa de importação",
        "Supremo Tribunal Federal julga ação sobre o tema",
    ]
    for s in samples:
        found = find_mentioned_politicians(s)
        print(f"{s!r} -> {[p['slug'] for p in found]}")


