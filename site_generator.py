"""
site_generator.py — gera um site estático simples (HTML) a partir do
histórico de commits do repositório, imitando a página de um repo no
GitHub: lista de "arquivos" (políticos) e o "log de commits" de cada um.

A página inicial (index.html) lista TODOS os políticos monitorados
(não só os que tiveram notícia recentemente) e tem busca por nome +
filtros por partido e por cargo, tudo em JavaScript puro no navegador
(sem backend, sem build step) — adequado para um site 100% estático
publicado no GitHub Pages.
"""

import json
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

  .filters { display: flex; gap: 10px; flex-wrap: wrap; margin: 20px 0; }
  .filters input, .filters select {
    padding: 8px 12px; border: 1px solid #d1d9e0; border-radius: 6px;
    font-size: 0.95em; font-family: inherit;
  }
  .filters input[type="text"] { flex: 1; min-width: 200px; }
  .filters button {
    padding: 8px 14px; border: 1px solid #d1d9e0; border-radius: 6px;
    background: #f6f8fa; cursor: pointer; font-size: 0.9em;
  }
  .filters button:hover { background: #eaeef2; }
  #result-count { color: #59636e; font-size: 0.9em; margin-bottom: 12px; }
  #no-results { display: none; color: #59636e; padding: 20px 0; }
</style>
"""


def _cargo_category(role: str) -> str:
    """Simplifica o campo 'role' (que pode incluir UF) numa categoria pro filtro."""
    role_lower = role.lower()
    if "ex-presidente" in role_lower:
        return "Ex-Presidente"
    if "presidente" in role_lower:
        return "Presidente da República"
    if "deputad" in role_lower:
        return "Deputado(a) Federal"
    if "senador" in role_lower:
        return "Senador(a)"
    if "ministr" in role_lower:
        return "Ministro(a)"
    if "governador" in role_lower:
        return "Governador(a)"
    return role  # fallback: usa o valor cru se não reconhecer nenhum padrão


def generate_index(site_dir: str = SITE_DIR) -> None:
    os.makedirs(site_dir, exist_ok=True)

    sorted_politicians = sorted(POLITICIANS, key=lambda p: p["name"])

    # Normaliza a caixa do partido só para o filtro/dropdown — evita
    # duplicatas como "Republicanos" (entrada manual) vs "REPUBLICANOS"
    # (API da Câmara/Senado, que retorna sempre em maiúsculas).
    parties = sorted(
        {p["party"].upper() for p in sorted_politicians if p["party"] and p["party"] != "-"}
    )
    cargos = sorted({_cargo_category(p["role"]) for p in sorted_politicians})

    rows = []
    for politician in sorted_politicians:
        log = get_log(politician)
        last_commit = log[0]["message"] if log else "sem commits ainda"
        cargo = _cargo_category(politician["role"])
        # Atributos data-* em minúsculo/sem aspas conflitantes para o JS de filtro ler.
        rows.append(
            f"""
            <div class="politician-card"
                 data-name="{politician['name'].lower()}"
                 data-party="{politician['party'].upper()}"
                 data-cargo="{cargo}">
              <a href="{politician['slug']}.html">{politician['name']}</a>
              <div class="meta">{politician['role']} · {politician['party']} · {len(log)} commits</div>
              <div class="meta">Último: {last_commit}</div>
            </div>
            """
        )

    party_options = "".join(f'<option value="{p}">{p}</option>' for p in parties)
    cargo_options = "".join(f'<option value="{c}">{c}</option>' for c in cargos)
    total = len(sorted_politicians)

    html = f"""<!DOCTYPE html>
<html lang="pt-br">
<head><meta charset="utf-8"><title>GitPolítica</title>{STYLE}</head>
<body>
  <h1>🏛️ GitPolítica</h1>
  <p class="meta">Um "GitHub" da política brasileira — cada político é um arquivo, cada notícia é um commit.</p>

  <div class="filters">
    <input type="text" id="search" placeholder="Buscar por nome..." oninput="applyFilters()">
    <select id="filter-party" onchange="applyFilters()">
      <option value="">Todos os partidos</option>
      {party_options}
    </select>
    <select id="filter-cargo" onchange="applyFilters()">
      <option value="">Todos os cargos</option>
      {cargo_options}
    </select>
    <button onclick="clearFilters()">Limpar filtros</button>
  </div>

  <div id="result-count">{total} de {total} políticos</div>
  <div id="cards-container">
    {''.join(rows)}
  </div>
  <div id="no-results">Nenhum político encontrado com esses filtros.</div>

  <script>
    const TOTAL = {total};

    function applyFilters() {{
      const query = document.getElementById('search').value.trim().toLowerCase();
      const party = document.getElementById('filter-party').value;
      const cargo = document.getElementById('filter-cargo').value;
      const cards = document.querySelectorAll('.politician-card');
      let visibleCount = 0;

      cards.forEach(card => {{
        const matchesName = !query || card.dataset.name.includes(query);
        const matchesParty = !party || card.dataset.party === party;
        const matchesCargo = !cargo || card.dataset.cargo === cargo;
        const show = matchesName && matchesParty && matchesCargo;
        card.style.display = show ? '' : 'none';
        if (show) visibleCount++;
      }});

      document.getElementById('result-count').textContent =
        visibleCount + ' de ' + TOTAL + ' políticos';
      document.getElementById('no-results').style.display =
        visibleCount === 0 ? 'block' : 'none';
    }}

    function clearFilters() {{
      document.getElementById('search').value = '';
      document.getElementById('filter-party').value = '';
      document.getElementById('filter-cargo').value = '';
      applyFilters();
    }}
  </script>
</body>
</html>"""

    with open(os.path.join(site_dir, "index.html"), "w", encoding="utf-8") as f:
        f.write(html)


def generate_politician_page(politician: dict, site_dir: str = SITE_DIR) -> None:
    log = get_log(politician)
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
