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

Duas formas de identificar a quem aplicar cada regra:

- `name_contains`: uma palavra (sem acento, minúscula) que precisa
  aparecer como palavra inteira no nome da pessoa. Boa pra sobrenomes
  bem distintivos, mas arriscada pra primeiros nomes comuns — ex.:
  "flavio" bateria tanto em "Flávio Bolsonaro" quanto em qualquer outro
  candidato chamado só "Flávio", recriando a mesma ambiguidade que o
  matcher já tenta evitar.
- `exact_name`: o nome (`name`) EXATO da pessoa, comparado após
  normalize() (sem acento, minúsculo). Mais seguro pra primeiros nomes
  comuns ou quando existe risco real de bater em mais de uma pessoa —
  use isso sempre que o alias extra for baseado só no primeiro nome.
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
    {
        # "flavio" sozinho (name_contains) bateria em qualquer outro
        # candidato de primeiro nome Flávio (ex.: "Dr Flávio") — usa
        # exact_name pra só afetar essa pessoa específica.
        "exact_name": "Flávio Bolsonaro",
        "aliases": ["Flávio"],
    },
]
