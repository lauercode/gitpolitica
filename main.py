"""
main.py — orquestra o pipeline completo do GitPolítica:

  1. Busca notícias (RSS)
  2. Identifica quais políticos monitorados são citados
  3. Grava cada menção como um commit real no repositório Git
  4. Regenera o site estático

Uso:
    python3 main.py                     # usa as fontes reais definidas em config.py
    python3 main.py --sample            # usa o feed de exemplo local (sample_feed.xml), sem internet
    python3 main.py --backend spacy     # usa NER via spaCy em vez do matcher por alias/fuzzy
                                         # (requer 'pip install spacy' + download do modelo pt,
                                         #  veja ner_spacy.py; cai de volta pro padrão se falhar)
    python3 main.py --summarize         # usa um LLM (API da Anthropic) para gerar a "commit
                                         # message" a partir do título+resumo da notícia, em vez
                                         # de usar o título cru (requer 'pip install anthropic' +
                                         # ANTHROPIC_API_KEY; cai de volta pro título se falhar)
"""

import sys
from config import RSS_SOURCES
from scraper import fetch_all_feeds, fetch_feed
from matcher import find_mentioned_politicians as find_mentioned_alias
from repo_writer import ensure_repo, commit_news, get_log
from site_generator import generate_site


def _get_matcher_function(backend: str):
    """Resolve qual função de identificação de políticos usar."""
    if backend == "spacy":
        try:
            from ner_spacy import find_mentioned_politicians_spacy
            # Testa se o modelo carrega antes de assumir que vai funcionar
            # no meio do processamento das notícias.
            find_mentioned_politicians_spacy("teste de carregamento do modelo")
            print("[backend] usando NER via spaCy")
            return find_mentioned_politicians_spacy
        except Exception as exc:  # noqa: BLE001
            print(f"[aviso] backend 'spacy' indisponível ({exc}); usando o padrão (alias/fuzzy)")
            return find_mentioned_alias

    print("[backend] usando matcher por alias/fuzzy (padrão, sem dependências)")
    return find_mentioned_alias


def run(use_sample: bool = False, backend: str = "alias", summarize: bool = False) -> None:
    ensure_repo()
    find_mentioned = _get_matcher_function(backend)

    if summarize:
        print("[resumo] usando LLM para gerar commit messages (fallback: título original)")
        from summarizer import generate_commit_message_safe

    if use_sample:
        print("[modo teste] usando sample_feed.xml (offline)")
        news_items = fetch_feed("Exemplo Fonte 1", "sample_feed.xml")
    else:
        news_items = fetch_all_feeds(RSS_SOURCES)

    print(f"{len(news_items)} notícias coletadas.")

    # Trava de segurança: uma notícia batendo em muitos políticos ao
    # mesmo tempo quase sempre é sinal de erro de correspondência (ex.:
    # uma lista de nomes/pesquisa eleitoral colidindo com apelidos
    # genéricos), não uma notícia genuinamente sobre todo mundo. Bug
    # real encontrado em produção: uma manchete de pesquisa Datafolha
    # gerou dezenas de commits errados antes dessa trava existir. Em vez
    # de arriscar um número mágico só de cabeça, o valor é configurável.
    MAX_MATCHES_POR_NOTICIA = 5

    total_commits = 0
    for item in news_items:
        matches = find_mentioned(item.full_text)

        if len(matches) > MAX_MATCHES_POR_NOTICIA:
            print(
                f"  [aviso] '{item.title[:80]}...' bateu em {len(matches)} "
                f"políticos (limite: {MAX_MATCHES_POR_NOTICIA}) — pulando "
                f"por segurança, provável erro de correspondência."
            )
            continue

        for politician in matches:
            # Evita recommitar a mesma notícia se o pipeline rodar de novo:
            # checagem simples pelo link já presente no log.
            existing = get_log(politician)
            if any(item.link in entry["message"] for entry in existing):
                continue
            if any(item.title in entry["message"] for entry in existing):
                continue

            headline = item.title
            if summarize:
                headline = generate_commit_message_safe(
                    politician_name=politician["name"],
                    headline=item.title,
                    body_text=item.summary,
                )

            commit_hash = commit_news(
                politician=politician,
                headline=headline,
                source_name=item.source_name,
                source_url=item.link,
                published_at=item.published_at,
            )
            total_commits += 1
            print(f"  + commit {commit_hash[:8]} em {politician['slug']}: {headline}")

    print(f"{total_commits} novos commits criados.")

    generate_site()
    print("Site regenerado em data/site/")


if __name__ == "__main__":
    backend = "spacy" if "--backend" in sys.argv and "spacy" in sys.argv else "alias"
    run(
        use_sample="--sample" in sys.argv,
        backend=backend,
        summarize="--summarize" in sys.argv,
    )
