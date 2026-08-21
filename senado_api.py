"""
senado_api.py — integração com a API de Dados Abertos do Senado Federal
(https://legis.senado.leg.br/dadosabertos/senador/lista/atual).

Diferente da API da Câmara, a do Senado responde em XML por padrão (dá
pra pedir JSON, mas o XML é mais previsível e já testamos o formato
real). Sem paginação: a lista de parlamentares em exercício vem inteira
numa só resposta (pouco mais de 80 registros, entre titulares e
suplentes atualmente em exercício).

Só biblioteca padrão (urllib + xml.etree), sem dependências externas.
"""

import urllib.request
import xml.etree.ElementTree as ET

from camara_api import slugify  # reaproveita a mesma função de slug
from text_utils import extract_surname

API_URL = "https://legis.senado.leg.br/dadosabertos/senador/lista/atual"


def fetch_senadores_xml() -> bytes:
    req = urllib.request.Request(API_URL, headers={"Accept": "application/xml"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        return resp.read()


def parse_senadores_xml(raw: bytes) -> list[dict]:
    """Faz parse do XML da lista de parlamentares em exercício."""
    root = ET.fromstring(raw)
    records = []
    for parlamentar in root.findall(".//Parlamentar"):
        ident = parlamentar.find("IdentificacaoParlamentar")
        if ident is None:
            continue
        records.append(
            {
                "id": ident.findtext("CodigoParlamentar"),
                "nome": ident.findtext("NomeParlamentar"),
                "siglaPartido": ident.findtext("SiglaPartidoParlamentar", "-"),
                "siglaUf": ident.findtext("UfParlamentar", ""),
            }
        )
    return records


def fetch_all_senadores() -> list[dict]:
    """Busca a lista completa de senadores(as) em exercício."""
    raw = fetch_senadores_xml()
    return parse_senadores_xml(raw)


def to_politician_dict(record: dict) -> dict:
    """Converte um registro cru da API no formato usado por config.py."""
    name = record["nome"]
    party = record.get("siglaPartido") or "-"
    uf = record.get("siglaUf", "")
    surname = extract_surname(name)
    aliases = [name]
    if surname != name and len(surname) > 3:
        aliases.append(surname)
    return {
        "slug": slugify(name),
        "name": name,
        "role": f"Senador(a) ({uf})" if uf else "Senador(a)",
        "party": party,
        "aliases": aliases,
        "senado_id": record.get("id"),
    }


def build_politicians_list(records: list[dict]) -> list[dict]:
    return [to_politician_dict(r) for r in records]


if __name__ == "__main__":
    records = fetch_all_senadores()
    for p in build_politicians_list(records)[:10]:
        print(p)
    print(f"... total: {len(records)} parlamentares em exercício")
