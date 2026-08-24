"""
repo_writer.py — grava cada notícia como um COMMIT de verdade num
repositório Git local. Cada político é um arquivo Markdown; cada
notícia vira uma linha adicionada ao arquivo + um commit com uma
mensagem no estilo "conventional commits" adaptado para política.

Isso é o coração do paralelo Git <-> Política:
  - arquivo         = político
  - commit          = notícia
  - commit message  = manchete/resumo
  - autor do commit = fonte jornalística
  - tag             = marco formal (posse, cassação, condenação...)
"""

import os
import subprocess
from datetime import datetime, timezone

from config import REPO_DIR, POLITICIANS


def _run_git(args: list[str], cwd: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True
    )
    if result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} falhou: {result.stderr}")
    return result.stdout.strip()


def ensure_repo(repo_dir: str = REPO_DIR) -> None:
    """
    Cria o repositório Git e os arquivos iniciais de cada político, se
    não existirem. Idempotente e seguro de rodar em CI: mesmo quando o
    repositório já foi clonado do GitHub (por exemplo, via
    actions/checkout numa run anterior — nesse caso o .git já existe,
    mas a identidade de commit local não vem configurada), a
    identidade do bot é sempre (re)aplicada.
    """
    os.makedirs(repo_dir, exist_ok=True)

    if not os.path.isdir(os.path.join(repo_dir, ".git")):
        subprocess.run(["git", "init", "-q"], cwd=repo_dir, check=True)

    # Sempre reaplica a identidade, mesmo em repo já existente (ver
    # docstring acima) — evitar "fatal: unable to auto-detect email".
    subprocess.run(["git", "config", "user.name", "gitpolitica-bot"], cwd=repo_dir, check=True)
    subprocess.run(["git", "config", "user.email", "bot@gitpolitica.local"], cwd=repo_dir, check=True)

    # Cria os arquivos que ainda não existem TODOS de uma vez, com um
    # único `git add` + `git commit` no final — não um commit por
    # político. Com a lista pequena (manual + Câmara + Senado, ~600),
    # isso não fazia diferença perceptível; com o dataset de
    # candidatos do TSE (dezenas de milhares), um commit por arquivo
    # tornaria o sync inicial impraticavelmente lento (cada `git
    # commit` sozinho já tem overhead de processo — multiplicado por
    # dezenas de milhares, viraria horas em vez de segundos).
    new_slugs = []
    for politician in POLITICIANS:
        filepath = os.path.join(repo_dir, f"{politician['slug']}.md")
        if not os.path.exists(filepath):
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(f"# {politician['name']}\n\n")
                f.write(f"- **Cargo**: {politician['role']}\n")
                f.write(f"- **Partido**: {politician['party']}\n\n")
                f.write("## Histórico\n\n")
            new_slugs.append(politician["slug"])

    if new_slugs:
        # `git add` só dos arquivos novos (não `git add .`, que poderia
        # varrer arquivos indesejados se algo mais estiver pendente no
        # working tree). Em lotes de 500 pra não estourar o limite de
        # tamanho da linha de comando com dezenas de milhares de nomes.
        batch_size = 500
        for i in range(0, len(new_slugs), batch_size):
            batch = new_slugs[i:i + batch_size]
            _run_git(["add"] + [f"{slug}.md" for slug in batch], cwd=repo_dir)

        if len(new_slugs) == 1:
            message = f"init: cria arquivo de {new_slugs[0]}"
        else:
            message = f"init: cria arquivo de {len(new_slugs)} políticos"
        _run_git(["commit", "-q", "-m", message], cwd=repo_dir)


def commit_news(
    politician_slug: str,
    headline: str,
    source_name: str,
    source_url: str,
    published_at: datetime | None = None,
    event_type: str = "news",
    repo_dir: str = REPO_DIR,
) -> str:
    """
    Adiciona uma notícia ao arquivo do político e cria um commit real.

    event_type segue a lógica de "conventional commits" adaptada:
      - news    -> notícia/declaração comum
      - merge   -> mudança de partido/aliança oficializada
      - release -> marco formal (posse, cassação, condenação, eleição)

    Retorna o hash do commit criado.
    """
    published_at = published_at or datetime.now(timezone.utc)
    date_str = published_at.strftime("%Y-%m-%d %H:%M UTC")

    filepath = os.path.join(repo_dir, f"{politician_slug}.md")
    if not os.path.exists(filepath):
        raise FileNotFoundError(
            f"Arquivo de {politician_slug} não existe. Rode ensure_repo() primeiro."
        )

    entry = (
        f"- **[{date_str}]** {headline}\n"
        f"  _fonte: [{source_name}]({source_url})_\n\n"
    )
    with open(filepath, "a", encoding="utf-8") as f:
        f.write(entry)

    prefix = {"news": "notícia", "merge": "merge", "release": "release"}[event_type]
    commit_message = f"{prefix}: {headline} (fonte: {source_name})"

    _run_git(["add", f"{politician_slug}.md"], cwd=repo_dir)
    _run_git(["commit", "-q", "-m", commit_message], cwd=repo_dir)
    commit_hash = _run_git(["rev-parse", "HEAD"], cwd=repo_dir)
    return commit_hash


def tag_release(politician_slug: str, tag_name: str, message: str, repo_dir: str = REPO_DIR) -> None:
    """Cria uma tag anotada para marcar um evento formal (posse, cassação, etc.)."""
    _run_git(["tag", "-a", tag_name, "-m", f"{politician_slug}: {message}"], cwd=repo_dir)


def get_log(politician_slug: str, repo_dir: str = REPO_DIR) -> list[dict]:
    """Retorna o histórico de commits de um político, mais recente primeiro."""
    output = _run_git(
        [
            "log",
            "--pretty=format:%H|%ad|%s",
            "--date=iso-strict",
            "--",
            f"{politician_slug}.md",
        ],
        cwd=repo_dir,
    )
    log = []
    if not output:
        return log
    for line in output.split("\n"):
        commit_hash, date, message = line.split("|", 2)
        log.append({"hash": commit_hash, "date": date, "message": message})
    return log


if __name__ == "__main__":
    ensure_repo()
    h = commit_news(
        politician_slug="lula",
        headline="Sanciona lei que amplia investimento em infraestrutura",
        source_name="Exemplo Fonte 1",
        source_url="https://exemplo.com/noticia/123",
    )
    print("Commit criado:", h)
    for entry in get_log("lula"):
        print(entry)
