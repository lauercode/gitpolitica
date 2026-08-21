"""
site_generator.py — gera um site estático simples (HTML) a partir do
histórico de commits do repositório, imitando a página de um repo no
GitHub: lista de "arquivos" (políticos) e o "log de commits" de cada um.
"""

import os
from config import POLITICIANS, REPO_DIR, SITE_DIR
from repo_writer import get_log

STYLE = """
<style>
  body { font-family: -apple-system, Segoe UI, Roboto, sans-serif; max-width: 900px; margin: 40px auto; padding: 0 20px; color: #1f2328; background: #fff; }
  h1 { border-bottom: 1px solid #d1d9e0; padding-bottom: 10px; }
  .politician-card { border: 1px solid #d1d9e0; border-radius: 8px; padding: 16px; margin-bottom: 16px; }
  .politician-card a { text-decoration: none; color: #0969da; font-weight: 600; font-size: 1.1em; }
  .meta { color: #59636e; font-size: 0.9em; }
  .commit { border-bottom: 1px solid #eaeef2; padding: 10px 0; }
  .commit:last-child { border-bottom: none; }
  .commit-msg { font-weight: 500; }
  .commit-hash { font-family: monospace; color: #59636e; font-size: 0.85em; }
  .commit-date { color: #59636e; font-size: 0.85em; }
  .back-link { display: inline-block; margin-bottom: 20px; }
</style>
"""


def generate_index(site_dir: str = SITE_DIR) -> None:
    os.makedirs(site_dir, exist_ok=True)
    rows = []
    for politician in POLITICIANS:
        log = get_log(politician["slug"])
        last_commit = log[0]["message"] if log else "sem commits ainda"
        rows.append(
            f"""
            <div class="politician-card">
              <a href="{politician['slug']}.html">{politician['name']}</a>
              <div class="meta">{politician['role']} · {politician['party']} · {len(log)} commits</div>
              <div class="meta">Último: {last_commit}</div>
            </div>
            """
        )

    html = f"""<!DOCTYPE html>
<html lang="pt-br">
<head><meta charset="utf-8"><title>GitPolítica</title>{STYLE}</head>
<body>
  <h1>🏛️ GitPolítica</h1>
  <p class="meta">Um "GitHub" da política brasileira — cada político é um arquivo, cada notícia é um commit.</p>
  {''.join(rows)}
</body>
</html>"""

    with open(os.path.join(site_dir, "index.html"), "w", encoding="utf-8") as f:
        f.write(html)


def generate_politician_page(politician: dict, site_dir: str = SITE_DIR) -> None:
    log = get_log(politician["slug"])
    commits_html = "".join(
        f"""
        <div class="commit">
          <div class="commit-msg">{entry['message']}</div>
          <div class="commit-hash">{entry['hash'][:8]}</div>
          <div class="commit-date">{entry['date']}</div>
        </div>
        """
        for entry in log
    ) or "<p>Nenhum commit registrado ainda.</p>"

    html = f"""<!DOCTYPE html>
<html lang="pt-br">
<head><meta charset="utf-8"><title>{politician['name']} — GitPolítica</title>{STYLE}</head>
<body>
  <a class="back-link" href="index.html">&larr; voltar</a>
  <h1>{politician['name']}</h1>
  <p class="meta">{politician['role']} · {politician['party']}</p>
  <h2>Histórico de commits</h2>
  {commits_html}
</body>
</html>"""

    with open(os.path.join(site_dir, f"{politician['slug']}.html"), "w", encoding="utf-8") as f:
        f.write(html)


def generate_site(site_dir: str = SITE_DIR) -> None:
    generate_index(site_dir)
    for politician in POLITICIANS:
        generate_politician_page(politician, site_dir)


if __name__ == "__main__":
    generate_site()
    print(f"Site gerado em {SITE_DIR}/")
