"""
extra_aliases.py — apelidos extras para políticos que já existem via
Câmara/Senado/TSE, mas cujo nome de urna de uma palavra só (ex:
"Lula") não vira alias automaticamente (ver text_utils/camara_api/
senado_api/tse_api — nomes de uma palavra só são excluídos da geração
automática de alias, pra evitar colisão em escala com o dataset do
TSE — bugs #8 e #10 do README).

Este arquivo NÃO cria políticos novos, papéis, partidos, etc. — só
ENRIQUECE os aliases de quem já existe via alguma outra fonte. Se a
pessoa referenciada aqui não existir mais em nenhuma fonte (ex.: não
está mais em exercício nem é candidata em 2026), a regra simplesmente
não tem efeito nenhum — não recria a pessoa do zero.

`name_contains` é uma palavra (sem acento, minúscula) que precisa
aparecer como palavra inteira no nome da pessoa (comparado após
normalize() — sem acento, minúsculo) pra decidir a quem aplicar os
aliases extras. Usar uma palavra distintiva o bastante pra não bater
com mais de uma pessoa por engano.
"""

EXTRA_ALIASES = [
    {
        "name_contains": "lula",
        "aliases": ["Lula", "presidente Lula"],
    },
    {
        "name_contains": "tarcisio",
        "aliases": ["Tarcísio", "governador Tarcísio"],
    },
]
