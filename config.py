"""
Configuração do GitPolítica MVP.

POLITICIANS combina três fontes:
  1. MANUAL_POLITICIANS — cargos que não vêm de nenhuma API do Congresso
     (Presidente, ministros do STF, governadores, etc.), mantidos à mão.
  2. <REPO_DIR>/_meta/politicians_camara.json — deputados, gerado por
     sync_politicians.py a partir da API da Câmara.
  3. <REPO_DIR>/_meta/politicians_senado.json — senadores, gerado por
     sync_politicians.py a partir da API do Senado.

Se os arquivos gerados não existirem ainda (sync nunca rodou), o
sistema funciona só com a lista manual.

IMPORTANTE: os arquivos gerados moram DENTRO de REPO_DIR (o
repositório de dados), não num caminho separado no repositório de
código. Isso é proposital — REPO_DIR é o único lugar que de fato
persiste entre execuções em produção (é ele que é clonado do GitHub a
cada run e recebe um `git push` no final). Um caminho fora dele seria
recriado do zero a cada execução do CI e a lista sincronizada se
perderia silenciosamente em toda run que não chamasse
sync_politicians.py — foi exatamente esse bug que motivou essa
reestruturação (ver README, seção "Bug de persistência").

Em caso de conflito de slug, a prioridade é: manual > Câmara > Senado
(por exemplo, um deputado que também aparece de alguma forma na lista
do Senado mantém a versão da Câmara).
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

MANUAL_POLITICIANS = [
    {
        "slug": "lula",
        "name": "Luiz Inácio Lula da Silva",
        "role": "Presidente da República",
        "party": "PT",
        "aliases": ["Lula", "Luiz Inácio Lula da Silva", "presidente Lula"],
    },
    {
        "slug": "jair-bolsonaro",
        "name": "Jair Bolsonaro",
        "role": "Ex-Presidente",
        "party": "PL",
        "aliases": ["Bolsonaro", "Jair Bolsonaro", "ex-presidente Bolsonaro"],
    },
    {
        "slug": "arthur-lira",
        "name": "Arthur Lira",
        "role": "Deputado Federal",
        "party": "PP",
        "aliases": ["Arthur Lira", "Lira"],
    },
    {
        "slug": "flavio-dino",
        "name": "Flávio Dino",
        "role": "Ministro do STF",
        "party": "-",
        "aliases": ["Flávio Dino", "ministro Dino"],
    },
    {
        "slug": "tarcisio-de-freitas",
        "name": "Tarcísio de Freitas",
        "role": "Governador de SP",
        "party": "Republicanos",
        "aliases": ["Tarcísio de Freitas", "Tarcísio", "governador Tarcísio"],
    },
]


def _load_json_list(path: str) -> list[dict]:
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def load_politicians() -> list[dict]:
    """Mescla MANUAL_POLITICIANS + Câmara + Senado, nessa ordem de prioridade."""
    merged = list(MANUAL_POLITICIANS)
    seen_slugs = {p["slug"] for p in merged}

    for source_path in (_CAMARA_PATH, _SENADO_PATH):
        for politician in _load_json_list(source_path):
            if politician["slug"] not in seen_slugs:
                merged.append(politician)
                seen_slugs.add(politician["slug"])

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