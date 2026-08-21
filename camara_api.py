"""
camara_api.py — integração com a API de Dados Abertos da Câmara dos
Deputados (https://dadosabertos.camara.leg.br/api/v2/deputados).

Usada para gerar automaticamente a lista de deputados monitorados,
em vez de mantê-la manualmente em config.py.

Só biblioteca padrão (urllib), sem dependências externas.
"""

import json
import re
import unicodedata
import urllib.request

from text_utils import extract_surname

API_URL = "https://dadosabertos.camara.leg.br/api/v2/deputados"


def slugify(name: str) -> str:
    """Converte 'Arthur Lira' em 'arthur-lira', removendo acentos."""
    normalized = unicodedata.normalize("NFKD", name)
    ascii_name = normalized.encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", ascii_name).strip("-").lower()
    return slug


def fetch_deputados_page(pagina: int = 1, itens: int = 100) -> list[dict]:
    """Busca uma página da lista de deputados em exercício."""
    url = f"{API_URL}?pagina={pagina}&itens={itens}&ordem=ASC&ordenarPor=nome"
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        payload = json.loads(resp.read())
    return payload.get("dados", [])


def fetch_all_deputados() -> list[dict]:
    """Busca todas as páginas de deputados em exercício (atualmente ~513)."""
    all_records = []
    pagina = 1
    while True:
        records = fetch_deputados_page(pagina=pagina)
        if not records:
            break
        all_records.extend(records)
        pagina += 1
    return all_records


def to_politician_dict(record: dict) -> dict:
    """
    Converte um registro cru da API no formato usado por config.py:
    {slug, name, role, party, aliases}
    """
    name = record["nome"]
    party = record.get("siglaPartido", "-")
    uf = record.get("siglaUf", "")
    surname = extract_surname(name)
    aliases = [name]
    if surname != name and len(surname) > 3:
        aliases.append(surname)
    return {
        "slug": slugify(name),
        "name": name,
        "role": f"Deputado(a) Federal ({uf})" if uf else "Deputado(a) Federal",
        "party": party,
        "aliases": aliases,
        "camara_id": record.get("id"),
    }


def build_politicians_list(records: list[dict]) -> list[dict]:
    return [to_politician_dict(r) for r in records]


if __name__ == "__main__":
    # Teste rápido: busca só a primeira página em produção.
    records = fetch_deputados_page(pagina=1, itens=10)
    for p in build_politicians_list(records):
        print(p)
