"""
ner_spacy.py — backend de NER "de verdade" usando spaCy, como upgrade
opcional sobre o matcher.py (que é 100% biblioteca padrão e não precisa
de instalação nenhuma).

IMPORTANTE: este módulo não foi testado no ambiente em que este projeto
foi gerado, porque esse ambiente não tem acesso à internet para instalar
o spaCy nem baixar o modelo de português. O código segue a documentação
oficial do spaCy e deve funcionar normalmente na sua máquina, mas rode
os testes no fim deste arquivo antes de usar em produção.

Instalação (no seu ambiente, com internet):
    pip install spacy
    python -m spacy download pt_core_news_lg

Por que usar isso além do matcher.py?
  - matcher.py só reconhece candidatos por um regex de "palavras
    capitalizadas" e casa contra a lista de políticos já cadastrados.
  - Este módulo usa um modelo de linguagem treinado para reconhecer
    entidades do tipo PESSOA de verdade, entendendo contexto
    gramatical. Isso permite, por exemplo, descobrir menções a
    políticos que AINDA NÃO estão na lista monitorada (útil para
    crescer a base automaticamente) — o matcher.py nunca vai encontrar
    alguém que não esteja em config.py, mas este módulo consegue listar
    "pessoas mencionadas que não bati com ninguém conhecido" para
    revisão manual.

Uso típico:
    from ner_spacy import extract_person_entities, resolve_entities

    entidades = extract_person_entities(texto)
    conhecidos, desconhecidos = resolve_entities(entidades)
    # conhecidos: políticos de config.py que foram encontrados
    # desconhecidos: nomes de pessoas mencionados que não bateram com
    #                 ninguém da lista — candidatos a adicionar
"""

import difflib

from config import POLITICIANS
from text_utils import normalize

_MODEL_NAME = "pt_core_news_lg"
_nlp = None  # carregado sob demanda (lazy), é pesado para importar


def _load_model():
    global _nlp
    if _nlp is not None:
        return _nlp
    try:
        import spacy
    except ImportError as exc:
        raise RuntimeError(
            "spaCy não está instalado. Rode: pip install spacy "
            "&& python -m spacy download pt_core_news_lg"
        ) from exc

    try:
        _nlp = spacy.load(_MODEL_NAME)
    except OSError as exc:
        raise RuntimeError(
            f"Modelo '{_MODEL_NAME}' não encontrado. Rode: "
            f"python -m spacy download {_MODEL_NAME}"
        ) from exc
    return _nlp


def extract_person_entities(text: str) -> list[str]:
    """
    Usa o modelo de NER do spaCy para extrair todas as entidades do
    tipo PESSOA (PER) mencionadas no texto.
    """
    nlp = _load_model()
    doc = nlp(text)
    return [ent.text for ent in doc.ents if ent.label_ == "PER"]


def resolve_entities(
    entity_names: list[str], threshold: float = 0.85
) -> tuple[list[dict], list[str]]:
    """
    Recebe uma lista de nomes de pessoa (já extraídos pelo spaCy) e
    tenta casar cada um contra os políticos monitorados, por
    similaridade de string (mesma técnica de matcher.py).

    Retorna (políticos_encontrados, nomes_não_reconhecidos). O segundo
    valor é valioso: são pessoas que o modelo identificou como PESSOA
    no texto, mas que não batem com ninguém da lista monitorada —
    candidatos a novos políticos para adicionar em config.py.
    """
    resolved = {}
    unresolved = []

    for entity_name in entity_names:
        entity_norm = normalize(entity_name)
        best_politician = None
        best_score = 0.0

        for politician in POLITICIANS:
            targets = [politician["name"]] + politician["aliases"]
            for target in targets:
                score = difflib.SequenceMatcher(
                    None, entity_norm, normalize(target)
                ).ratio()
                if score > best_score:
                    best_score = score
                    best_politician = politician

        if best_politician and best_score >= threshold:
            resolved[best_politician["slug"]] = best_politician
        else:
            unresolved.append(entity_name)

    return list(resolved.values()), unresolved


def find_mentioned_politicians_spacy(text: str) -> list[dict]:
    """Interface equivalente a matcher.find_mentioned_politicians(), via spaCy."""
    entities = extract_person_entities(text)
    resolved, _unresolved = resolve_entities(entities)
    return resolved


if __name__ == "__main__":
    # Só roda se spaCy + modelo estiverem instalados no seu ambiente.
    samples = [
        "O deputado Arthur Lira se reuniu com o presidente Lula ontem.",
        "Segundo apurou a reportagem, João da Silva Pereira, morador "
        "local, testemunhou o acidente.",  # nome desconhecido, não deve resolver
    ]
    for s in samples:
        entities = extract_person_entities(s)
        resolved, unresolved = resolve_entities(entities)
        print(f"{s!r}")
        print(f"  entidades PER encontradas: {entities}")
        print(f"  resolvidos: {[p['slug'] for p in resolved]}")
        print(f"  não reconhecidos (candidatos a nova entrada): {unresolved}")
