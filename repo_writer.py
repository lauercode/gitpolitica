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

ORGANIZAÇÃO DE ARQUIVOS: cada político fica em `<UF>/<slug>.md` (ex:
`SP/arthur-lira.md`), não solto na raiz do repositório — necessário na
escala do TSE (~40 mil candidatos ficariam ilegíveis numa única pasta
no GitHub). Políticos sem UF (Presidente, ministros do STF) ficam em
`nacional/`. Ver text_utils.extract_uf() e migrate_to_uf_folders.py
(para reorganizar um repositório de dados já existente no formato
antigo, "achatado").
"""

import os
import re
import subprocess
from datetime import datetime, timezone

import config as _config
from config import REPO_DIR
from text_utils import extract_uf


def _run_git(args: list[str], cwd: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True
    )
    if result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} falhou: {result.stderr}")
    return result.stdout.strip()


def get_politician_relative_path(politician: dict) -> str:
    """Caminho relativo do arquivo de um político dentro do repositório de dados."""
    uf = extract_uf(politician.get("role", ""))
    return f"{uf}/{politician['slug']}.md"


def ensure_repo(repo_dir: str = REPO_DIR) -> None:
    """
    Cria o repositório Git e os arquivos iniciais de cada político, se
    não existirem. Idempotente e seguro de rodar em CI: mesmo quando o
    repositório já foi clonado do GitHub (por exemplo, via
    actions/checkout numa run anterior — nesse caso o .git já existe,
    mas a identidade de commit local não vem configurada), a
    identidade do bot é sempre (re)aplicada.

    IMPORTANTE — bug real encontrado em produção: esta função recarrega
    a lista de políticos NA HORA (`_config.load_politicians()`), em vez
    de usar um `POLITICIANS` importado uma única vez no topo do
    arquivo. `config.POLITICIANS` só é calculado quando o módulo
    `config` é importado pela primeira vez — se `ensure_repo()` for
    chamada ANTES de `sync_politicians.py` escrever os JSONs mais
    recentes de Câmara/Senado/TSE na mesma execução (exatamente a
    ordem que `run()` usava), ela criaria arquivos só para quem já
    existia ANTES do sync começar, deixando de fora qualquer candidato
    novo ou corrigido naquela mesma rodada — bug real que explicava
    ~20 mil arquivos de política "faltando" mesmo com o JSON do TSE
    já atualizado.
    """
    politicians = _config.load_politicians()

    os.makedirs(repo_dir, exist_ok=True)

    if not os.path.isdir(os.path.join(repo_dir, ".git")):
        subprocess.run(["git", "init", "-q"], cwd=repo_dir, check=True)

    # Sempre reaplica a identidade, mesmo em repo já existente (ver
    # docstring acima) — evitar "fatal: unable to auto-detect email".
    subprocess.run(["git", "config", "user.name", "gitpolitica-bot"], cwd=repo_dir, check=True)
    subprocess.run(["git", "config", "user.email", "bot@gitpolitica.local"], cwd=repo_dir, check=True)

    # Cria os arquivos que ainda não existem TODOS de uma vez, com um
    # único `git add` + `git commit` no final — não um commit por
    # político (ver histórico do projeto: com dezenas de milhares de
    # candidatos do TSE, um commit por arquivo tornaria o sync inicial
    # impraticavelmente lento).
    new_paths = []
    for politician in politicians:
        relative_path = get_politician_relative_path(politician)
        filepath = os.path.join(repo_dir, relative_path)
        if not os.path.exists(filepath):
            os.makedirs(os.path.dirname(filepath), exist_ok=True)
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(f"# {politician['name']}\n\n")
                f.write(f"- **Cargo**: {politician['role']}\n")
                f.write(f"- **Partido**: {politician['party']}\n\n")
                f.write("## Histórico\n\n")
            new_paths.append(relative_path)

    if new_paths:
        # `git add` só dos arquivos novos (não `git add .`, que poderia
        # varrer arquivos indesejados se algo mais estiver pendente no
        # working tree). Em lotes de 500 pra não estourar o limite de
        # tamanho da linha de comando com dezenas de milhares de nomes.
        batch_size = 500
        for i in range(0, len(new_paths), batch_size):
            batch = new_paths[i:i + batch_size]
            _run_git(["add"] + batch, cwd=repo_dir)

        if len(new_paths) == 1:
            message = f"init: cria arquivo de {new_paths[0]}"
        else:
            message = f"init: cria arquivo de {len(new_paths)} políticos"
        _run_git(["commit", "-q", "-m", message], cwd=repo_dir)


def commit_news(
    politician: dict,
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

    relative_path = get_politician_relative_path(politician)
    filepath = os.path.join(repo_dir, relative_path)
    if not os.path.exists(filepath):
        raise FileNotFoundError(
            f"Arquivo de {politician['slug']} não existe em {relative_path}. "
            "Rode ensure_repo() primeiro."
        )

    entry = (
        f"- **[{date_str}]** {headline}\n"
        f"  _fonte: [{source_name}]({source_url})_\n\n"
    )
    with open(filepath, "a", encoding="utf-8") as f:
        f.write(entry)

    prefix = {"news": "notícia", "merge": "merge", "release": "release"}[event_type]
    commit_message = f"{prefix}: {headline} (fonte: {source_name})"

    _run_git(["add", relative_path], cwd=repo_dir)
    _run_git(["commit", "-q", "-m", commit_message], cwd=repo_dir)
    commit_hash = _run_git(["rev-parse", "HEAD"], cwd=repo_dir)
    return commit_hash


def tag_release(politician: dict, tag_name: str, message: str, repo_dir: str = REPO_DIR) -> None:
    """Cria uma tag anotada para marcar um evento formal (posse, cassação, etc.)."""
    _run_git(["tag", "-a", tag_name, "-m", f"{politician['slug']}: {message}"], cwd=repo_dir)


def get_log(politician: dict, repo_dir: str = REPO_DIR) -> list[dict]:
    """Retorna o histórico de commits de um político, mais recente primeiro."""
    relative_path = get_politician_relative_path(politician)
    output = _run_git(
        [
            "log",
            "--pretty=format:%H|%ad|%s",
            "--date=iso-strict",
            "--",
            relative_path,
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


_ENTRY_PATTERN = re.compile(
    r"- \*\*\[(?P<date>[^\]]+)\]\*\* (?P<headline>.+?)\n"
    r"  _fonte: \[(?P<source_name>[^\]]+)\]\((?P<source_url>[^)]+)\)_"
)


def get_historico_entries(politician: dict, repo_dir: str = REPO_DIR) -> list[dict]:
    """
    Lê o arquivo .md do político diretamente e extrai cada entrada de
    histórico (data, manchete, fonte E link) — diferente de get_log(),
    que só lê metadados do commit (hash/data/mensagem) e não tem o link
    da notícia, já que o link mora no CONTEÚDO do arquivo, não na
    mensagem do commit. Ordenado do mais recente pro mais antigo.
    """
    relative_path = get_politician_relative_path(politician)
    filepath = os.path.join(repo_dir, relative_path)
    if not os.path.exists(filepath):
        return []

    with open(filepath, encoding="utf-8") as f:
        content = f.read()

    entries = [m.groupdict() for m in _ENTRY_PATTERN.finditer(content)]
    entries.reverse()  # arquivo tem ordem cronológica; queremos mais recente primeiro
    return entries


def get_all_commit_counts(repo_dir: str = REPO_DIR) -> dict[str, int]:
    """
    Conta quantos commits tocaram cada arquivo de político, com UMA
    chamada de `git log` pro repositório inteiro — muito mais rápido
    que chamar get_log() individualmente pra cada um (inviável em
    escala com dezenas de milhares de políticos). Usado pelas páginas
    de categoria do site pra permitir ordenar por número de notícias.
    """
    output = _run_git(["log", "--pretty=format:", "--name-only"], cwd=repo_dir)
    counts: dict[str, int] = {}
    for line in output.split("\n"):
        line = line.strip()
        if line.endswith(".md"):
            counts[line] = counts.get(line, 0) + 1
    return counts


if __name__ == "__main__":
    from config import POLITICIANS
    lula = next(p for p in POLITICIANS if p["slug"] == "lula")

    ensure_repo()
    h = commit_news(
        politician=lula,
        headline="Sanciona lei que amplia investimento em infraestrutura",
        source_name="Exemplo Fonte 1",
        source_url="https://exemplo.com/noticia/123",
    )
    print("Commit criado:", h)
    print("Caminho do arquivo:", get_politician_relative_path(lula))
    for entry in get_log(lula):
        print(entry)
