"""
tse_api.py — integração com o dataset "Candidatos - 2026" do Portal de
Dados Abertos do TSE (https://dadosabertos.tse.jus.br/dataset/candidatos-2026).

Diferente da Câmara/Senado, isso NÃO é uma API JSON/XML — é um arquivo
ZIP contendo um CSV com TODOS os candidatos registrados para a eleição
de 2026 (Presidente, Governador, Senador, Deputado Federal, Deputado
Estadual/Distrital), atualizado pelo TSE conforme os registros de
candidatura são processados. O prazo de registro de candidatura para
2026 encerrou em 15/08, então o dataset já deve estar substancialmente
completo.

IMPORTANTE — leia antes de rodar em produção: este módulo não pôde ser
testado contra o arquivo real neste ambiente (o sandbox onde este
projeto foi gerado não tem acesso à internet para baixar/abrir o ZIP).
O parser segue o layout de colunas documentado publicamente pelo TSE,
que é estável há vários ciclos eleitorais, mas NÃO foi validado
byte-a-byte contra o arquivo de 2026. Rode o bloco de teste no fim
deste arquivo (`python3 tse_api.py`) no seu ambiente antes de confiar
nele em produção — se alguma coluna tiver mudado de nome, o KeyError
vai apontar exatamente qual.

⚠️ ESCALA: candidatos a Deputado Estadual/Distrital em todo o país
somam dezenas de milhares de registros. Isso é MUITO maior que a
Câmara/Senado (~600 pessoas) e exige as otimizações feitas em
repo_writer.bulk_create_files() (commit único em lote, não um commit
por pessoa) e no índice por prefixo do matcher.py — sem isso, o sync
inicial deste dataset seria impraticavelmente lento.
"""

import csv
import io
import re
import urllib.request
import zipfile

from camara_api import slugify
from text_utils import extract_surname, has_title_prefix

CANDIDATOS_ZIP_URL = (
    "https://cdn.tse.jus.br/estatistica/sead/odsele/consulta_cand/consulta_cand_2026.zip"
)

# Situações de candidatura consideradas "ativas" — candidaturas
# claramente rejeitadas/canceladas/renunciadas ficam de fora. Qualquer
# status não reconhecido por nenhuma das duas listas é MANTIDO (com um
# aviso), pra evitar perder registros válidos por um rótulo que o TSE
# mudou ou que não previmos.
_STATUS_EXCLUIR = ("INDEFERID", "CANCELAD", "RENUNCIA", "FALECID", "INAPTO")
_STATUS_INCLUIR = ("DEFERID", "APTO")

# Cargos incluídos nesta sincronização (o usuário optou por TODOS,
# incluindo Deputado Estadual — o grupo de maior volume).
_CARGOS_INCLUIDOS = (
    "PRESIDENTE",
    "GOVERNADOR",
    "SENADOR",
    "DEPUTADO FEDERAL",
    "DEPUTADO ESTADUAL",
    "DEPUTADO DISTRITAL",
)


def fetch_candidatos_zip(url: str = CANDIDATOS_ZIP_URL) -> bytes:
    # CDNs de sites de governo (o TSE provavelmente usa Akamai ou
    # Cloudflare) costumam bloquear requisições que não "parecem" vir
    # de um navegador de verdade — um User-Agent sozinho às vezes não
    # basta; um conjunto mais completo de cabeçalhos típicos de
    # navegador (Accept, Accept-Language, Referer apontando pra página
    # do dataset) reduz a chance de bloqueio. Não há garantia: alguns
    # bloqueios são por fingerprinting de TLS, que não dá pra
    # contornar só com cabeçalhos — nesse caso, use
    # fetch_candidatos_zip_from_file() com um download manual.
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
            ),
            "Accept": "application/zip, application/octet-stream, */*",
            "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
            "Referer": "https://dadosabertos.tse.jus.br/dataset/candidatos-2026",
        },
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        return resp.read()


def fetch_candidatos_zip_from_file(path: str) -> bytes:
    """
    Alternativa a fetch_candidatos_zip() para quando o download
    automático é bloqueado pelo CDN do TSE (comum — ver comentário
    acima). Baixe o arquivo manualmente pelo navegador em
    https://dadosabertos.tse.jus.br/dataset/candidatos-2026 e passe o
    caminho local aqui.
    """
    with open(path, "rb") as f:
        return f.read()


def _open_all_csvs_from_zip(zip_bytes: bytes) -> list[csv.DictReader]:
    """
    Abre TODOS os arquivos .csv encontrados dentro do zip — o TSE
    costuma dividir esse dataset em um CSV por UF (27 arquivos) em vez
    de um único arquivo nacional combinado. Uma versão anterior deste
    módulo só lia `csv_names[0]` (o primeiro arquivo, tipicamente "AC"
    por ordem alfabética) e processava só aquele estado — bug real
    encontrado em produção: retornava ~558 candidatos em vez de dezenas
    de milhares. Corrigido para agregar todos os arquivos.

    Encoding latin-1 e delimitador ';' são o padrão histórico dos
    arquivos de dados abertos do TSE.
    """
    zf = zipfile.ZipFile(io.BytesIO(zip_bytes))
    csv_names = [name for name in zf.namelist() if name.lower().endswith(".csv")]
    if not csv_names:
        raise RuntimeError("Nenhum arquivo .csv encontrado dentro do zip do TSE.")

    readers = []
    for name in csv_names:
        raw = zf.read(name)
        text = raw.decode("latin-1")
        readers.append(csv.DictReader(io.StringIO(text), delimiter=";"))
    return readers


def _situacao_ativa(situacao: str) -> tuple[bool, bool]:
    """Retorna (deve_incluir, status_reconhecido)."""
    situacao_upper = situacao.upper()
    if any(s in situacao_upper for s in _STATUS_EXCLUIR):
        return False, True
    if any(s in situacao_upper for s in _STATUS_INCLUIR):
        return True, True
    return True, False  # desconhecido: inclui, mas sinaliza


def parse_candidatos_csv(reader: csv.DictReader) -> list[dict]:
    """
    Processa o CSV de candidatos, filtrando por cargo (_CARGOS_INCLUIDOS)
    e por situação de candidatura ativa. Imprime progresso a cada 5000
    linhas, já que o arquivo tem dezenas de milhares de registros.
    """
    records = []
    unrecognized_status = set()

    for i, row in enumerate(reader, start=1):
        if i % 5000 == 0:
            print(f"  ... {i} linhas processadas")

        cargo = (row.get("DS_CARGO") or "").strip().upper()
        if cargo not in _CARGOS_INCLUIDOS:
            continue

        situacao = row.get("DS_SITUACAO_CANDIDATURA") or ""
        incluir, reconhecido = _situacao_ativa(situacao)
        if not reconhecido:
            unrecognized_status.add(situacao)
        if not incluir:
            continue

        records.append(row)

    if unrecognized_status:
        print(
            f"  [aviso] {len(unrecognized_status)} status de candidatura não "
            f"reconhecidos (incluídos mesmo assim): {sorted(unrecognized_status)}"
        )

    return records


def to_politician_dict(row: dict) -> dict:
    """Converte uma linha do CSV do TSE no formato usado por config.py."""
    nome_urna = (row.get("NM_URNA_CANDIDATO") or "").strip()
    nome_civil = (row.get("NM_CANDIDATO") or "").strip()
    nome = nome_urna or nome_civil
    partido = (row.get("SG_PARTIDO") or "-").strip()
    uf = (row.get("SG_UE") or row.get("SG_UF") or "").strip()
    cargo = (row.get("DS_CARGO") or "").strip().title()

    aliases = set()
    if nome_civil and nome_civil != nome:
        aliases.add(nome_civil)

    if " " in nome:
        # Nome de urna com 2+ palavras: trata normalmente, incluindo o
        # sobrenome como alias extra (quando não é um nome de urna com
        # título/patente, que já sabemos que engana a heurística).
        aliases.add(nome)
        surname = extract_surname(nome)
        if surname != nome and len(surname) > 3 and not has_title_prefix(nome):
            aliases.add(surname)
    # Nome de urna de UMA PALAVRA SÓ (ex: "Superman", "Duda", "Ana") não
    # vira alias sozinho — bug real encontrado em produção: é comum
    # candidatos registrarem um apelido curto e genérico como nome de
    # urna pra chamar atenção na cadeira eleitoral, e numa base de ~40
    # mil candidatos, sempre existe alguém assim cujo "nome inteiro" é
    # uma palavra comum o bastante pra colidir com qualquer menção não
    # relacionada em texto de notícia (ex.: "Ana" batendo dentro de
    # "Ana Luiza", uma pessoa completamente diferente). O preço: esses
    # candidatos só são encontrados pelo nome civil (se distinto do
    # nome de urna) — não há solução geral sem uma lista de nomes
    # comuns do português pra saber quais palavras são "seguras".

    # Remove acentos antes de gerar o slug — bug real encontrado em
    # produção: sem isso, nomes como "Marília" viravam slugs corrompidos
    # como "mar-lia" (o acento virava só um hífen solto).
    slug_base = slugify(nome)

    return {
        "slug": slug_base,
        "name": nome,
        "role": f"Candidato(a) a {cargo} ({uf}) — Eleição 2026",
        "party": partido,
        "aliases": sorted(aliases),
        "tse_sequencial": row.get("SQ_CANDIDATO"),
    }


def build_politicians_list(records: list[dict]) -> list[dict]:
    """
    Converte os registros crus em dicts de político, deduplicando slugs
    repetidos (pode acontecer com nomes de urna idênticos em UFs
    diferentes) ao anexar a UF no slug do segundo em diante.
    """
    seen_slugs: dict[str, int] = {}
    politicians = []

    for row in records:
        politician = to_politician_dict(row)
        slug = politician["slug"]
        if slug in seen_slugs:
            seen_slugs[slug] += 1
            uf = (row.get("SG_UE") or row.get("SG_UF") or "").strip().lower()
            politician["slug"] = f"{slug}-{uf}-{seen_slugs[slug]}"
        else:
            seen_slugs[slug] = 0
        politicians.append(politician)

    return politicians


def fetch_and_build(local_zip_path: str | None = None) -> list[dict]:
    """
    Ponto de entrada principal: baixa (ou lê de um arquivo local, se
    `local_zip_path` for informado — útil quando o download automático
    é bloqueado pelo CDN do TSE), filtra e converte tudo de uma vez.
    """
    if local_zip_path:
        print(f"Lendo dataset de candidatos 2026 do TSE a partir de {local_zip_path}...")
        zip_bytes = fetch_candidatos_zip_from_file(local_zip_path)
    else:
        print("Baixando dataset de candidatos 2026 do TSE (pode demorar, arquivo grande)...")
        zip_bytes = fetch_candidatos_zip()
    print(f"  {len(zip_bytes) / 1_000_000:.1f} MB baixados. Extraindo CSV(s)...")
    readers = _open_all_csvs_from_zip(zip_bytes)
    print(f"  {len(readers)} arquivo(s) CSV encontrado(s) dentro do zip.")

    records = []
    for i, reader in enumerate(readers, start=1):
        print(f"  processando arquivo {i}/{len(readers)}...")
        records.extend(parse_candidatos_csv(reader))
    print(f"  {len(records)} candidaturas ativas nos cargos monitorados (total, todos os arquivos).")
    return build_politicians_list(records)


if __name__ == "__main__":
    # Teste rápido com um CSV sintético (mesma estrutura de colunas do
    # TSE), pra validar o parsing sem precisar baixar o arquivo real.
    sample_csv = (
        "DS_CARGO;DS_SITUACAO_CANDIDATURA;NM_CANDIDATO;NM_URNA_CANDIDATO;"
        "SG_PARTIDO;SG_UF;SG_UE\n"
        "PRESIDENTE;DEFERIDO;Fulano de Tal Silva;Fulano Silva;PXX;BR;BR\n"
        "GOVERNADOR;DEFERIDO COM RECURSO;Ciclana Souza;Ciclana;PYY;SP;SP\n"
        "DEPUTADO ESTADUAL;INDEFERIDO;Beltrano Nunca Sai;Beltrano;PZZ;RJ;RJ\n"
        "DEPUTADO FEDERAL;DEFERIDO;Outra Pessoa;Outra Pessoa;PXX;MG;MG\n"
        "VEREADOR;DEFERIDO;Nao Monitorado;Nao Monitorado;PXX;SP;SP\n"
    )
    reader = csv.DictReader(io.StringIO(sample_csv), delimiter=";")
    records = parse_candidatos_csv(reader)
    politicians = build_politicians_list(records)
    print(f"\n{len(politicians)} políticos de teste construídos (esperado: 3):")
    for p in politicians:
        print(f"  {p}")
