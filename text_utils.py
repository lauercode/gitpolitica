"""
text_utils.py — utilitários de normalização de texto compartilhados.
"""

import re
import unicodedata


def strip_accents(text: str) -> str:
    """Remove acentos/diacríticos, preservando o restante do texto."""
    normalized = unicodedata.normalize("NFKD", text)
    return "".join(c for c in normalized if not unicodedata.combining(c))


def normalize(text: str) -> str:
    """Normaliza para comparação: sem acentos, minúsculo, espaços colapsados."""
    return " ".join(strip_accents(text).lower().split())


def extract_surname(full_name: str) -> str:
    """
    Extrai o último token do nome como "sobrenome" candidato.
    Ex: 'Flávio Bolsonaro' -> 'Bolsonaro'.

    É uma heurística simples (nomes brasileiros nem sempre seguem esse
    padrão), mas suficiente para gerar um alias curto adicional que o
    matcher pode usar — a desambiguação por contexto (disambiguation.py)
    é o que garante que isso não vire falso positivo quando o sobrenome
    for compartilhado por mais de um político monitorado.
    """
    tokens = full_name.strip().split()
    return tokens[-1] if tokens else full_name


# Nomes de urna no padrão "Título/Patente + Primeiro Nome" são comuns
# no Brasil (candidatos ligados à segurança pública, forças armadas ou
# religião costumam usar isso para se identificar no voto). Nesse
# padrão, extract_surname() erra: o "último token" na verdade é um
# primeiro nome comum (ex: "Coronel Fernanda" -> "Fernanda"), não um
# sobrenome de verdade — e "Fernanda" sozinho colide com qualquer
# pessoa não-política de primeiro nome igual (ex: atrizes Fernanda
# Montenegro, Maria Fernanda Cândido). Bug real encontrado em produção.
_PREFIXOS_TITULO_PATENTE = {
    "coronel", "capitao", "sargento", "delegado", "delegada", "major",
    "tenente", "cabo", "soldado", "doutor", "doutora", "professor",
    "professora", "pastor", "pastora", "padre", "policial", "juiz",
    "juiza", "promotor", "promotora", "advogado", "advogada",
}


def has_title_prefix(full_name: str) -> bool:
    """
    True se o primeiro token do nome for um título/patente conhecido —
    sinal de que extract_surname() não deve ser usado para gerar um
    alias automático (o resultado seria um primeiro nome comum, não um
    sobrenome distintivo).
    """
    tokens = full_name.strip().split()
    if not tokens:
        return False
    return normalize(tokens[0]) in _PREFIXOS_TITULO_PATENTE


_UF_PATTERN = re.compile(r"\(([A-Z]{2})\)")
_UFS_VALIDAS = {
    "AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO", "MA", "MT",
    "MS", "MG", "PA", "PB", "PR", "PE", "PI", "RJ", "RN", "RS", "RO",
    "RR", "SC", "SP", "SE", "TO",
}


def extract_uf(role: str) -> str:
    """
    Extrai a sigla de UF do campo "role" de um político (ex:
    "Deputado(a) Federal (SP)" -> "SP"). Usado para organizar os
    arquivos do repositório de dados em subpastas por estado, em vez
    de todos juntos na raiz — necessário na escala do TSE (~40 mil
    candidatos ficariam ilegíveis numa pasta só no GitHub).

    Retorna "nacional" para políticos sem UF no cargo (Presidente,
    Ex-Presidente, ministros do STF) ou quando o padrão não é
    reconhecido.
    """
    match = _UF_PATTERN.search(role or "")
    if match and match.group(1) in _UFS_VALIDAS:
        return match.group(1)
    return "nacional"
