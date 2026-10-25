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
    "tenente", "cabo", "soldado", "doutor", "doutora", "dr", "dra",
    "professor", "professora", "pastor", "pastora", "padre", "policial",
    "juiz", "juiza", "promotor", "promotora", "advogado", "advogada",
    "escritor", "escritora", "cantor", "cantora", "radialista",
    "empresario", "empresaria", "medico", "medica", "enfermeiro",
    "enfermeira", "bombeiro", "motorista", "agricultor", "agricultora",
    "pescador", "pescadora", "missionario", "missionaria", "apostolo",
    "bispo", "frei", "irmao", "irma", "engenheiro", "engenheira",
    "dentista", "veterinario", "veterinaria", "psicologo", "psicologa",
}

# Palavras comuns do português que, mesmo capitalizadas (ex.: início de
# frase/manchete), NÃO devem virar alias de correspondência — bugs
# reais encontrados em produção: "Troca" (sobrenome de Adilson Troca)
# e "Cidadania" (parte do nome de urna de outro candidato) capturavam
# qualquer manchete começando com essas palavras comuns ("Troca de
# fios de energia...", "Cidadania" como tema genérico de notícia),
# mesmo com o casamento de uma palavra já sendo case-sensitive — o
# problema persiste quando a palavra comum começa a frase (capitalizada
# por regra gramatical normal, não por ser um nome próprio). Lista não
# exaustiva — adicionar aqui conforme novos casos aparecerem.
_PALAVRAS_COMUNS_BLOQUEADAS = {
    "troca", "trocas", "cidadania", "crise", "cores", "dias", "tinha",
    "contas", "portas", "fortes", "marcas", "cidade", "cidades",
    "trabalho", "mestre", "nossa", "jato", "lava",
}

# Sobrenomes de figuras públicas reais MUITO conhecidas que não são
# candidatas nem estão em exercício em cargo eletivo (então nunca
# entram na nossa lista de políticos monitorados) — mas que aparecem
# constantemente no noticiário, criando colisão com candidatos
# monitorados que por acaso têm o mesmo sobrenome. Caso real: Marcelo
# Moraes (candidato) recebendo notícias sobre o ministro do STF
# Alexandre de Moraes. Lista pequena e curada à mão — os ministros do
# STF são o caso mais claro e enumerável (11 pessoas, composição muda
# raramente). Revisar periodicamente.
_SOBRENOMES_FIGURAS_NAO_MONITORADAS = {
    "moraes", "mendonca", "fux", "barroso", "zanin", "fachin",
    "toffoli",
}


def is_blocked_alias_word(word: str) -> bool:
    """
    True se `word` (normalizado — sem acento, minúsculo) nunca deve
    virar um alias de correspondência de uma palavra só, mesmo sendo
    um sobrenome/nome de urna real de algum candidato — combina as
    duas listas acima (palavras comuns do português + sobrenomes de
    figuras públicas famosas não monitoradas).
    """
    return word in _PALAVRAS_COMUNS_BLOQUEADAS or word in _SOBRENOMES_FIGURAS_NAO_MONITORADAS


def has_title_prefix(full_name: str) -> bool:
    """
    True se o primeiro token do nome for um título/patente conhecido.
    Ver has_no_real_surname() — essa função sozinha não diferencia
    "Coronel Fernanda" (sem sobrenome de verdade) de "Escritor Augusto
    Cury" (tem sobrenome de verdade, só precedido de uma profissão) —
    use has_no_real_surname() pra decidir se gera alias de sobrenome.
    """
    tokens = full_name.strip().split()
    if not tokens:
        return False
    return normalize(tokens[0]) in _PREFIXOS_TITULO_PATENTE


def has_no_real_surname(full_name: str) -> bool:
    """
    True só quando, depois de remover um título/profissão reconhecido
    do início, sobra UM token só — sinal de que não existe sobrenome
    de verdade (ex.: "Coronel Fernanda" -> sobra só "Fernanda", que é
    primeiro nome, não sobrenome). Bug real corrigido: usar só
    has_title_prefix() pra essa decisão bloqueava também casos como
    "Escritor Augusto Cury", onde sobra "Augusto Cury" — um Nome +
    Sobrenome de verdade — e o alias de sobrenome ("Cury") deveria
    continuar sendo gerado normalmente.
    """
    tokens = full_name.strip().split()
    if not tokens:
        return False
    if normalize(tokens[0]) not in _PREFIXOS_TITULO_PATENTE:
        return False
    return len(tokens[1:]) <= 1


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


_CARGO_WRAPPER_PATTERN = re.compile(
    r"^Candidato\(a\) a (.+?) \([A-Z]{2}\)(?: — Eleição \d{4})?$"
)
_UF_SUFFIX_PATTERN = re.compile(r"\s*\([A-Z]{2}\)\s*$")
_GENERO_NEUTRO_PATTERN = re.compile(r"\((?:a|o)\)")


def extract_cargo_category(role: str) -> str:
    """
    Extrai o cargo diretamente do texto do "role" — sem lista fixa de
    categorias possíveis. Movido de site_generator.py pra cá pra ser
    reaproveitado também por disambiguation.py (usado na desambiguação
    por "co-menção de pares do mesmo cargo" — ver
    disambiguation._peer_comention_bonus()).
    """
    role = (role or "").strip()

    match = _CARGO_WRAPPER_PATTERN.match(role)
    if match:
        cargo_text = match.group(1)
    else:
        cargo_text = _UF_SUFFIX_PATTERN.sub("", role).strip() or role

    cargo_text = _GENERO_NEUTRO_PATTERN.sub("", cargo_text)
    return " ".join(cargo_text.split())


_CONECTORES_NOME = {"de", "da", "do", "dos", "das", "e", "di", "du"}


def smart_title_case(text: str) -> str:
    """
    Converte um nome TODO EM MAIÚSCULAS (como o TSE entrega os nomes de
    urna: "ESCRITOR AUGUSTO CURY") para capitalização normal ("Escritor
    Augusto Cury"), mantendo conectores minúsculos ("Tarcísio de
    Freitas"). Só mexe em texto totalmente maiúsculo — nomes que já
    vêm com capitalização normal (Câmara/Senado) passam intactos.

    Bug real: o casamento de aliases de UMA PALAVRA é sensível a
    maiúsculas (para "Dias" não bater em "dias"), então um alias
    "CURY" nunca casava com "Cury" no texto da notícia.
    """
    if not text or not text.isupper():
        return text

    def cap(word: str) -> str:
        return "-".join(part[:1].upper() + part[1:].lower() for part in word.split("-"))

    words = text.split(" ")
    out = []
    for i, w in enumerate(words):
        out.append(w.lower() if (i > 0 and w.lower() in _CONECTORES_NOME) else cap(w))
    return " ".join(out)
