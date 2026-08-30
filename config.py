"""
Configuração do GitPolítica MVP.

POLITICIANS combina três fontes (o MANUAL_POLITICIANS foi removido —
Câmara, Senado e TSE já cobrem todo mundo que é candidato ou está em
exercício; quem não é nenhum dos dois, como um ex-presidente inelegível
ou um ministro do STF sem candidatura, simplesmente não é mais
monitorado):
  1. <REPO_DIR>/_meta/politicians_camara.json — deputados, gerado por
     sync_politicians.py a partir da API da Câmara.
  2. <REPO_DIR>/_meta/politicians_senado.json — senadores, gerado por
     sync_politicians.py a partir da API do Senado.
  3. <REPO_DIR>/_meta/politicians_tse.json — candidatos à eleição de
     2026 (Presidente, Governador, Senador, Deputado Federal, Deputado
     Estadual/Distrital), gerado a partir do dataset de Dados Abertos
     do TSE. Esta fonte é MUITO maior que as outras duas somadas
     (dezenas de milhares de registros) — ver tse_api.py.

Se os arquivos gerados não existirem ainda (sync nunca rodou), a lista
fica vazia — este projeto não tem mais nenhuma lista embutida no
código.

IMPORTANTE: os arquivos gerados moram DENTRO de REPO_DIR (o
repositório de dados), não num caminho separado no repositório de
código. Isso é proposital — REPO_DIR é o único lugar que de fato
persiste entre execuções em produção (é ele que é clonado do GitHub a
cada run e recebe um `git push` no final). Um caminho fora dele seria
recriado do zero a cada execução do CI e a lista sincronizada se
perderia silenciosamente em toda run que não chamasse
sync_politicians.py — foi exatamente esse bug que motivou essa
reestruturação (ver README, seção "Bug de persistência").

Em caso de conflito de slug, a prioridade é: Câmara > Senado > TSE.
Além disso, candidatos do TSE cujo NOME normalizado já bate com alguém
das outras duas fontes não ganham um arquivo/entrada separada — a
entrada existente é marcada com `is_2026_candidate = True` e
`candidacy_role` (ver docstring de load_politicians()), permitindo que
o site liste a pessoa tanto como "em exercício" quanto como
"candidato", sem duplicar o histórico Git dela.

Aliases extras (curados manualmente, mas só o alias — não a pessoa
inteira) para gente cujo nome de urna de uma palavra só não gera alias
automático, ver extra_aliases.py.
"""

import json
import os

# Podem ser sobrescritos por variável de ambiente — útil em CI, onde o
# repositório de dados é clonado num caminho específico pelo
# actions/checkout (veja .github/workflows/update.yml).
REPO_DIR = os.environ.get("GITPOLITICA_REPO_DIR", "data/repo")
SITE_DIR = os.environ.get("GITPOLITICA_SITE_DIR", "data/site")

# Ver docstring do módulo: precisam morar dentro de REPO_DIR.
_CAMARA_PATH = os.path.join(REPO_DIR, "_meta", "politicians_camara.json")
_SENADO_PATH = os.path.join(REPO_DIR, "_meta", "politicians_senado.json")
_TSE_PATH = os.path.join(REPO_DIR, "_meta", "politicians_tse.json")


def _load_json_list(path: str) -> list[dict]:
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _apply_extra_aliases(politicians: list[dict]) -> None:
    """
    Enriquece (in-place) os aliases de quem bate com alguma regra de
    extra_aliases.py — não cria ninguém novo, só adiciona alias em
    quem já existe via alguma fonte. Ver extra_aliases.py.
    """
    import re
    from extra_aliases import EXTRA_ALIASES
    from text_utils import normalize

    for politician in politicians:
        norm_name = normalize(politician["name"])
        for rule in EXTRA_ALIASES:
            pattern = rf"\b{re.escape(rule['name_contains'])}\b"
            if re.search(pattern, norm_name):
                existing = set(politician["aliases"])
                for alias in rule["aliases"]:
                    if alias not in existing:
                        politician["aliases"].append(alias)
                        existing.add(alias)


def load_politicians() -> list[dict]:
    """
    Mescla Câmara + Senado + TSE, nessa ordem de prioridade. Um
    candidato do TSE cujo nome já existe nas duas primeiras fontes NÃO
    ganha um arquivo/entrada separada (mesma pessoa — um arquivo
    duplicado reintroduziria o problema que a deduplicação por nome
    resolveu). Em vez disso, a entrada já existente (de mandato) é
    marcada com `is_2026_candidate = True` e `candidacy_role` (o cargo
    ao qual está concorrendo) — assim site_generator.py consegue listar
    essa pessoa tanto no card de "Em exercício" quanto no de
    "Candidatos 2026", sem duplicar o histórico Git dela.

    Cada político é marcado com "source" (camara/senado/tse) — usado
    por matcher.py para excluir o TSE (dezenas de milhares de
    registros) da camada de fuzzy matching multi-palavra, que só é
    segura em escala menor e curada (bug real de colisão em produção).
    """
    from text_utils import normalize

    merged = []
    seen_slugs: set[str] = set()

    for source_path, source_name in ((_CAMARA_PATH, "camara"), (_SENADO_PATH, "senado")):
        for politician in _load_json_list(source_path):
            if politician["slug"] not in seen_slugs:
                merged.append({**politician, "source": source_name, "is_2026_candidate": False})
                seen_slugs.add(politician["slug"])

    # Mapeia slug/nome normalizado -> referência ao dict já em `merged`,
    # pra poder marcar (mutar) a entrada existente quando encontrarmos
    # a candidatura correspondente de 2026, em vez de só checar
    # presença e pular.
    slug_to_politician = {p["slug"]: p for p in merged}
    seen_names = {normalize(p["name"]): p for p in merged}

    for politician in _load_json_list(_TSE_PATH):
        norm_name = normalize(politician["name"])

        # Pode bater por slug (caso mais comum — o slug vem do mesmo
        # nome) OU só por nome (slugs gerados de formas ligeiramente
        # diferentes pra mesma pessoa).
        existing = slug_to_politician.get(politician["slug"]) or seen_names.get(norm_name)

        if existing is not None:
            existing["is_2026_candidate"] = True
            existing["candidacy_role"] = politician.get("role")
            continue

        new_entry = {**politician, "source": "tse", "is_2026_candidate": True}
        merged.append(new_entry)
        slug_to_politician[politician["slug"]] = new_entry
        seen_names[norm_name] = new_entry

    _apply_extra_aliases(merged)

    return merged


POLITICIANS = load_politicians()

# Fontes de notícias (RSS).

RSS_SOURCES = [
    {
        "name": "Agência Brasil - Política",
        "url": "http://agenciabrasil.ebc.com.br/rss/politica/feed.xml",
    },
    {
        "name": "Agência Câmara - Política",
        "url": "https://www.camara.leg.br/noticias/rss/dinamico/POLITICA",
    },
    {
        "name": "G1 - Política:",
        "url": "https://g1.globo.com/dynamo/politica/rss2.xml",
    },
    {
        "name": "Folha de S.Paulo - Em cima da hora",
        "url": "https://feeds.folha.uol.com.br/emcimadahora/rss091.xml",
    },
    {
        "name": "Gazeta do Povo - República",
        "url": "https://www.gazetadopovo.com.br/feed/rss/republica.xml",
    },
    {
        "name": "Gazeta do Povo - Congresso Nacional",
        "url": "https://www.gazetadopovo.com.br/feed/rss/tudo-sobre/congresso-nacional.xml",
    },
    {
        "name": "Gazeta do Povo - Governo Federal",
        "url": "https://www.gazetadopovo.com.br/feed/rss/tudo-sobre/governo-federal.xml",
    },
    {
        "name": "BBC Brasil - Primeira Página",
        "url": "http://www.bbc.co.uk/portuguese/index.xml",
    },
    {
        "name": "BBC Brasil - Brasil",
        "url": "http://www.bbc.co.uk/portuguese/topicos/brasil/index.xml",
    },
]
