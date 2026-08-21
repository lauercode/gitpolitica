"""
text_utils.py — utilitários de normalização de texto compartilhados.
"""

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
