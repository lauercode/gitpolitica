"""
summarizer.py — gera a "commit message" de cada notícia usando um LLM
(API da Anthropic), em vez de usar o título cru da notícia.

IMPORTANTE: assim como ner_spacy.py, este módulo não pôde ser testado
de ponta a ponta no ambiente em que este projeto foi gerado — não há
acesso à internet nem uma API key configurada aqui. O código segue a
documentação oficial do SDK da Anthropic e deve funcionar no seu
ambiente, mas teste antes de confiar nele em produção (rode o bloco
`if __name__ == "__main__"` no fim deste arquivo).

Por que usar um LLM aqui?
  - O título de uma notícia às vezes é clickbait, vago, ou não captura
    o fato principal ("Motta faz declaração forte sobre pauta" em vez
    de "Motta anuncia pauta prioritária do semestre").
  - Um resumo gerado a partir do título + descrição consegue produzir
    uma "commit message" mais parecida com o estilo Git real: curta,
    no imperativo/presente, focada no fato, sem sensacionalismo.

Configuração necessária no seu ambiente:
    pip install anthropic
    export ANTHROPIC_API_KEY="sua-chave-aqui"

Uso típico:
    from summarizer import generate_commit_message

    mensagem = generate_commit_message(
        politician_name="Hugo Motta",
        headline="Hugo Motta afirma que nova lei fortalece atuação do STJ",
        body_text="Norma regulamenta o filtro de relevância...",
    )
    # mensagem: "sanciona lei que regulamenta filtro de relevância no STJ"
"""

import os

# Modelo pequeno e rápido — adequado para uma tarefa de resumo curto e
# repetitiva. Ver system prompt / documentação da Anthropic para a
# lista atual de modelos disponíveis via API.
_MODEL_NAME = "claude-haiku-4-5-20251001"

_SYSTEM_PROMPT = """\
Você resume notícias políticas brasileiras em uma única linha, no estilo \
de uma mensagem de commit do Git: curta, factual, sem sensacionalismo, \
começando com um verbo no presente (ex: "sanciona", "vota contra", \
"anuncia", "nega", "critica"). Responda APENAS com a frase resumida, \
sem aspas, sem ponto final, com no máximo 100 caracteres. Não repita o \
nome do político no início da frase (ele já é conhecido pelo contexto). \
Não invente fatos que não estejam no texto fornecido."""


def _client():
    """Cria o cliente da Anthropic sob demanda (lazy import)."""
    try:
        import anthropic
    except ImportError as exc:
        raise RuntimeError(
            "O pacote 'anthropic' não está instalado. Rode: pip install anthropic"
        ) from exc

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError(
            "ANTHROPIC_API_KEY não está definida no ambiente. "
            "Rode: export ANTHROPIC_API_KEY='sua-chave-aqui'"
        )

    return anthropic.Anthropic(api_key=api_key)


def generate_commit_message(
    politician_name: str, headline: str, body_text: str = ""
) -> str:
    """
    Gera uma mensagem de commit curta e factual a partir do título (e,
    se disponível, do resumo/corpo) de uma notícia.

    Lança RuntimeError se o SDK não estiver instalado ou a API key não
    estiver configurada — quem chama decide se quer capturar e usar o
    título cru como fallback (veja main.py para o padrão recomendado).
    """
    client = _client()

    user_content = f"Político: {politician_name}\nTítulo: {headline}"
    if body_text:
        user_content += f"\nResumo: {body_text}"

    response = client.messages.create(
        model=_MODEL_NAME,
        max_tokens=60,
        system=_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_content}],
    )

    text = "".join(
        block.text for block in response.content if block.type == "text"
    ).strip()

    # Salvaguarda: se por algum motivo vier vazio ou gigante, não usa.
    if not text or len(text) > 150:
        raise RuntimeError(f"Resposta do modelo inválida ou vazia: {text!r}")

    return text


def generate_commit_message_safe(
    politician_name: str, headline: str, body_text: str = ""
) -> str:
    """
    Mesma coisa que generate_commit_message(), mas nunca lança exceção:
    se qualquer coisa der errado (SDK ausente, sem API key, erro de
    rede, resposta inválida), cai de volta para o título cru da notícia.
    Essa é a função que main.py usa por padrão.
    """
    try:
        return generate_commit_message(politician_name, headline, body_text)
    except Exception as exc:  # noqa: BLE001
        print(f"[aviso] resumo via LLM falhou ({exc}); usando título original")
        return headline


if __name__ == "__main__":
    # Só roda de ponta a ponta se anthropic + ANTHROPIC_API_KEY estiverem
    # configurados no seu ambiente.
    exemplo = generate_commit_message(
        politician_name="Hugo Motta",
        headline="Hugo Motta afirma que nova lei fortalece atuação do STJ em recursos especiais",
        body_text="Norma regulamenta o filtro de relevância para recursos especiais e define critérios para análise pelo tribunal",
    )
    print(f"Mensagem gerada: {exemplo!r}")
