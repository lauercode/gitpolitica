"""
git_events.py — modela dois tipos de evento político usando mecanismos
REAIS do Git, além do commit simples que repo_writer.commit_news() já
faz para notícias comuns:

1. TROCA DE PARTIDO -> git merge de verdade (--no-ff)

   Fluxo: cria uma branch a partir da branch principal, registra a
   mudança nela (atualiza o campo "Partido" no arquivo do político +
   adiciona uma entrada no histórico), volta pra branch principal e
   faz `git merge --no-ff` da branch de volta. Isso cria um commit de
   merge de verdade (com dois pais no grafo do Git), o equivalente
   mais fiel possível ao paralelo original: uma dissidência (fork)
   que se reintegra ao "projeto" através de um merge.

2. MARCO FORMAL (posse, cassação, condenação, eleição...) -> tag anotada

   Usa repo_writer.tag_release(), que já existia mas não estava
   conectada a nada. Aqui ela é chamada logo depois de um commit
   dedicado ao marco, então a tag aponta exatamente para o commit que
   registra o evento.

IMPORTANTE — por que isso não roda automaticamente sobre as notícias
do RSS: decidir "esta notícia é uma troca de partido, de X para Y" ou
"esta notícia é uma cassação" a partir de texto livre é um problema de
classificação/extração não trivial (fora do escopo do matcher.py, que
só faz reconhecimento de entidade). Errar aqui tem um custo alto: uma
troca de partido incorreta na história reescreveria um fato central
sobre o político. Por isso, essas funções são construídas para uso
CURADO — chamadas manualmente (por você, ou por um humano revisando
uma sugestão automática) depois de confirmar os detalhes, não para
serem disparadas cegamente pelo pipeline de notícias em main.py.

Veja record_event.py para uma interface de linha de comando que usa
essas funções.
"""

import os
import re
import subprocess
from datetime import datetime, timezone

from config import REPO_DIR
from repo_writer import _run_git, commit_news, tag_release


def _current_branch(repo_dir: str = REPO_DIR) -> str:
    return _run_git(["symbolic-ref", "--short", "HEAD"], cwd=repo_dir)


def _slugify_branch_component(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def _update_party_field(filepath: str, new_party: str) -> None:
    with open(filepath, encoding="utf-8") as f:
        content = f.read()

    updated, count = re.subn(
        r"(- \*\*Partido\*\*: ).*", rf"\g<1>{new_party}", content, count=1
    )
    if count == 0:
        raise RuntimeError(
            f"Não encontrei a linha '- **Partido**:' em {filepath}; "
            "o arquivo pode ter um formato inesperado."
        )

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(updated)


def record_party_change(
    politician_slug: str,
    politician_name: str,
    old_party: str,
    new_party: str,
    headline: str,
    source_name: str,
    source_url: str,
    published_at: datetime | None = None,
    repo_dir: str = REPO_DIR,
) -> str:
    """
    Registra uma troca de partido como um merge Git de verdade.

    Retorna o hash do commit de merge criado. Levanta exceção (e tenta
    voltar a branch principal) se algo der errado no meio do processo,
    para nunca deixar o repositório "preso" numa branch secundária.
    """
    published_at = published_at or datetime.now(timezone.utc)
    date_str = published_at.strftime("%Y-%m-%d")
    main_branch = _current_branch(repo_dir)
    branch_name = (
        f"partido/{politician_slug}/"
        f"{_slugify_branch_component(new_party)}-{date_str}"
    )

    try:
        _run_git(["checkout", "-q", "-b", branch_name], cwd=repo_dir)

        filepath = os.path.join(repo_dir, f"{politician_slug}.md")
        _update_party_field(filepath, new_party)

        entry = (
            f"- **[{date_str}]** MUDANÇA DE PARTIDO: {old_party} → {new_party}. "
            f"{headline}\n"
            f"  _fonte: [{source_name}]({source_url})_\n\n"
        )
        with open(filepath, "a", encoding="utf-8") as f:
            f.write(entry)

        _run_git(["add", f"{politician_slug}.md"], cwd=repo_dir)
        _run_git(
            [
                "commit",
                "-q",
                "-m",
                f"chore: atualiza partido de {politician_name} para {new_party}",
            ],
            cwd=repo_dir,
        )

        _run_git(["checkout", "-q", main_branch], cwd=repo_dir)
        merge_message = (
            f"merge: {politician_name} migra de {old_party} para {new_party} "
            f"(fonte: {source_name})"
        )
        _run_git(
            ["merge", "--no-ff", "-q", "-m", merge_message, branch_name],
            cwd=repo_dir,
        )
        _run_git(["branch", "-d", branch_name], cwd=repo_dir)

        return _run_git(["rev-parse", "HEAD"], cwd=repo_dir)

    except Exception:
        # Tenta não deixar o repo "preso" numa branch secundária.
        try:
            _run_git(["checkout", "-q", main_branch], cwd=repo_dir)
        except Exception:  # noqa: BLE001
            pass
        raise


def record_milestone(
    politician_slug: str,
    tag_name: str,
    tag_message: str,
    headline: str,
    source_name: str,
    source_url: str,
    published_at: datetime | None = None,
    repo_dir: str = REPO_DIR,
) -> str:
    """
    Registra um marco formal (posse, cassação, condenação, eleição...)
    como um commit dedicado + uma tag anotada apontando pra ele.

    Retorna o hash do commit criado (a tag aponta pra ele).
    """
    commit_hash = commit_news(
        politician_slug=politician_slug,
        headline=headline,
        source_name=source_name,
        source_url=source_url,
        published_at=published_at,
        event_type="release",
        repo_dir=repo_dir,
    )
    tag_release(politician_slug, tag_name, tag_message, repo_dir=repo_dir)
    return commit_hash


if __name__ == "__main__":
    # Demonstração de ponta a ponta com um CENÁRIO DE TESTE FICTÍCIO —
    # não é uma notícia real, só existe para provar que o merge e a tag
    # funcionam de verdade no Git. Veja o README para como isso se
    # conecta (manualmente) a eventos reais.
    from repo_writer import ensure_repo, get_log

    ensure_repo()

    merge_hash = record_party_change(
        politician_slug="arthur-lira",
        politician_name="Arthur Lira",
        old_party="PP",
        new_party="PARTIDO-TESTE",
        headline="[CENÁRIO DE TESTE, não é notícia real] migra de partido",
        source_name="Cenário de teste",
        source_url="https://exemplo.com/teste",
    )
    print(f"Merge de troca de partido criado: {merge_hash[:8]}")

    milestone_hash = record_milestone(
        politician_slug="arthur-lira",
        tag_name="v-teste-marco-ficticio",
        tag_message="[CENÁRIO DE TESTE, não é notícia real] marco formal fictício",
        headline="[CENÁRIO DE TESTE] toma posse em cargo fictício",
        source_name="Cenário de teste",
        source_url="https://exemplo.com/teste",
    )
    print(f"Commit de marco criado: {milestone_hash[:8]}")

    print("\nHistórico de arthur-lira após os dois eventos:")
    for entry in get_log("arthur-lira"):
        print(f"  {entry['hash'][:8]}  {entry['message']}")
