"""
site_generator.py — gera um site estático simples (HTML) a partir do
histórico de commits do repositório, imitando a página de um repo no
GitHub: lista de "arquivos" (políticos) e o "log de commits" de cada um.

ESTRUTURA (redesenhada para escala — com o TSE, o site passou de ~20
políticos pra mais de 20 mil "arquivos"):

  - index.html: só 3 cards de categoria (Em exercício / Candidatos
    2026 / Outros cargos), sem listar político nenhum diretamente —
    uma página com 20 mil cards HTML ficava grande e lenta demais.
  - <categoria>.html: uma página por categoria, com busca + filtros
    (nome, partido, cargo, UF) e PAGINAÇÃO client-side em JavaScript —
    os dados de todos os políticos daquela categoria vêm embutidos
    como um array JSON na página, mas só uma página de resultados (50
    por vez) é de fato renderizada no DOM a cada momento.
  - <slug>.html: continua uma página por político, com o histórico de
    commits completo (inalterado).

Para manter a geração do site rápida mesmo com ~20 mil políticos, as
páginas de categoria NÃO chamam get_log() para cada um (isso exigiria
20 mil subprocessos `git log`, lento demais) — só mostram nome,
partido, cargo e UF. O histórico completo de commits só é buscado na
página individual de cada político (uma chamada get_log() por vez,
sob demanda).
"""

import json
import os
from config import POLITICIANS, REPO_DIR, SITE_DIR
from repo_writer import get_log
from text_utils import extract_uf

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

  .category-grid { display: flex; flex-direction: column; gap: 16px; margin-top: 24px; }
  .category-card {
    display: block; border: 1px solid #d1d9e0; border-radius: 10px;
    padding: 24px; text-decoration: none; color: inherit;
  }
  .category-card:hover { background: #f6f8fa; border-color: #0969da; }
  .category-card h2 { margin: 0 0 6px 0; color: #0969da; font-size: 1.3em; }
  .category-card p { margin: 0; color: #59636e; }
  .category-count { font-weight: 700; font-size: 1.4em; color: #1f2328; }

  .pagination { display: flex; align-items: center; gap: 12px; justify-content: center; margin: 24px 0; }
  .pagination button {
    padding: 8px 16px; border: 1px solid #d1d9e0; border-radius: 6px;
    background: #f6f8fa; cursor: pointer; font-size: 0.9em;
  }
  .pagination button:disabled { opacity: 0.4; cursor: default; }
  .pagination button:not(:disabled):hover { background: #eaeef2; }
</style>
"""

# Categorias de alto nível, baseadas na origem de cada político — ver
# config.load_politicians(), que marca cada um com "source".
_CATEGORIAS = [
    {
        "key": "eleitos",
        "matches": lambda p: p.get("source") in {"camara", "senado"},
        "titulo": "Em exercício — Câmara e Senado",
        "descricao": "Deputados federais e senadores atualmente em exercício.",
    },
    {
        "key": "candidatos",
        "matches": lambda p: p.get("source") == "tse" or p.get("is_2026_candidate"),
        "titulo": "Candidatos à Eleição 2026",
        "descricao": (
            "Presidente, governadores, senadores, deputados federais e "
            "estaduais registrados para a eleição de 2026 — inclui quem já "
            "tem mandato e está concorrendo à reeleição ou a outro cargo."
        ),
        # Mostra o cargo/UF da CANDIDATURA aqui, não do mandato atual —
        # relevante pra quem tem os dois (ex.: deputado concorrendo ao
        # Senado). Nas outras categorias, o "role" normal já é o certo.
        "use_candidacy_role": True,
    },
    {
        "key": "outros",
        "matches": lambda p: p.get("source") == "manual",
        "titulo": "Outros cargos",
        "descricao": "Presidência, ministros do STF, governadores e demais cargos especiais.",
    },
]

_PAGE_SIZE = 50


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


def _politician_summary(politician: dict, use_candidacy_role: bool = False) -> dict:
    """
    Resumo leve (sem tocar no Git) usado nas páginas de categoria. Se
    `use_candidacy_role` e a pessoa tiver uma candidatura registrada
    (`candidacy_role` — quem já tem mandato E está concorrendo em
    2026), usa o cargo/UF da CANDIDATURA em vez do mandato atual, já
    que essa é a informação relevante na página de candidatos.
    """
    role_for_display = politician.get("role", "")
    if use_candidacy_role and politician.get("candidacy_role"):
        role_for_display = politician["candidacy_role"]

    return {
        "slug": politician["slug"],
        "name": politician["name"],
        "party": (politician.get("party") or "-").upper(),
        "cargo": _cargo_category(role_for_display),
        "uf": extract_uf(role_for_display),
    }


def _fmt_br(n: int) -> str:
    """Formata um número com separador de milhar no padrão brasileiro (ponto)."""
    return f"{n:,}".replace(",", ".")


def generate_index(site_dir: str = SITE_DIR) -> None:
    os.makedirs(site_dir, exist_ok=True)

    cards = []
    for categoria in _CATEGORIAS:
        count = sum(1 for p in POLITICIANS if categoria["matches"](p))
        cards.append(
            f"""
            <a class="category-card" href="{categoria['key']}.html">
              <h2>{categoria['titulo']}</h2>
              <p>{categoria['descricao']}</p>
              <p class="category-count">{_fmt_br(count)} político(a)s</p>
            </a>
            """
        )

    total = len(POLITICIANS)
    html = f"""<!DOCTYPE html>
<html lang="pt-br">
<head><meta charset="utf-8"><title>GitPolítica</title>{STYLE}</head>
<body>
  <h1>🏛️ GitPolítica</h1>
  <p class="meta">Um "GitHub" da política brasileira — cada político é um arquivo, cada notícia é um commit.</p>
  <p class="meta">{_fmt_br(total)} políticos monitorados no total.</p>
  <div class="category-grid">
    {''.join(cards)}
  </div>
</body>
</html>"""

    with open(os.path.join(site_dir, "index.html"), "w", encoding="utf-8") as f:
        f.write(html)


def generate_category_page(categoria: dict, site_dir: str = SITE_DIR) -> None:
    use_candidacy_role = categoria.get("use_candidacy_role", False)
    politicians = [p for p in POLITICIANS if categoria["matches"](p)]
    summaries = [_politician_summary(p, use_candidacy_role) for p in politicians]
    summaries.sort(key=lambda p: p["name"])

    parties = sorted({p["party"] for p in summaries if p["party"] and p["party"] != "-"})
    cargos = sorted({p["cargo"] for p in summaries})
    ufs = sorted({p["uf"] for p in summaries})

    party_options = "".join(f'<option value="{p}">{p}</option>' for p in parties)
    cargo_options = "".join(f'<option value="{c}">{c}</option>' for c in cargos)
    uf_options = "".join(f'<option value="{u}">{u}</option>' for u in ufs)

    data_json = json.dumps(summaries, ensure_ascii=False)

    html = f"""<!DOCTYPE html>
<html lang="pt-br">
<head><meta charset="utf-8"><title>{categoria['titulo']} — GitPolítica</title>{STYLE}</head>
<body>
  <a class="back-link" href="index.html">&larr; voltar</a>
  <h1>{categoria['titulo']}</h1>
  <p class="meta">{categoria['descricao']}</p>

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
    <select id="filter-uf" onchange="applyFilters()">
      <option value="">Todos os estados</option>
      {uf_options}
    </select>
    <button onclick="clearFilters()">Limpar filtros</button>
  </div>

  <div id="result-count"></div>
  <div id="cards-container"></div>
  <div id="no-results">Nenhum político encontrado com esses filtros.</div>

  <div class="pagination">
    <button id="prev-page" onclick="goToPage(-1)">&larr; Anterior</button>
    <span id="page-info"></span>
    <button id="next-page" onclick="goToPage(1)">Próxima &rarr;</button>
  </div>

  <script>
    const DATA = {data_json};
    const PAGE_SIZE = {_PAGE_SIZE};
    let filtered = DATA;
    let currentPage = 1;

    function applyFilters() {{
      const query = document.getElementById('search').value.trim().toLowerCase();
      const party = document.getElementById('filter-party').value;
      const cargo = document.getElementById('filter-cargo').value;
      const uf = document.getElementById('filter-uf').value;

      filtered = DATA.filter(p => {{
        const matchesName = !query || p.name.toLowerCase().includes(query);
        const matchesParty = !party || p.party === party;
        const matchesCargo = !cargo || p.cargo === cargo;
        const matchesUf = !uf || p.uf === uf;
        return matchesName && matchesParty && matchesCargo && matchesUf;
      }});

      currentPage = 1;
      render();
    }}

    function clearFilters() {{
      document.getElementById('search').value = '';
      document.getElementById('filter-party').value = '';
      document.getElementById('filter-cargo').value = '';
      document.getElementById('filter-uf').value = '';
      applyFilters();
    }}

    function goToPage(delta) {{
      const totalPages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
      currentPage = Math.min(Math.max(1, currentPage + delta), totalPages);
      render();
    }}

    function render() {{
      const totalPages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
      const start = (currentPage - 1) * PAGE_SIZE;
      const pageItems = filtered.slice(start, start + PAGE_SIZE);

      const container = document.getElementById('cards-container');
      container.innerHTML = pageItems.map(p => `
        <div class="politician-card">
          <a href="${{p.slug}}.html">${{p.name}}</a>
          <div class="meta">${{p.cargo}} (${{p.uf}}) · ${{p.party}}</div>
        </div>
      `).join('');

      document.getElementById('result-count').textContent =
        filtered.length.toLocaleString('pt-BR') + ' político(a)s encontrados';
      document.getElementById('no-results').style.display =
        filtered.length === 0 ? 'block' : 'none';
      document.getElementById('page-info').textContent =
        'Página ' + currentPage + ' de ' + totalPages;
      document.getElementById('prev-page').disabled = currentPage <= 1;
      document.getElementById('next-page').disabled = currentPage >= totalPages;
    }}

    render();
  </script>
</body>
</html>"""

    with open(os.path.join(site_dir, f"{categoria['key']}.html"), "w", encoding="utf-8") as f:
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
    for categoria in _CATEGORIAS:
        generate_category_page(categoria, site_dir)
    for politician in POLITICIANS:
        generate_politician_page(politician, site_dir)


if __name__ == "__main__":
    generate_site()
    print(f"Site gerado em {SITE_DIR}/")
