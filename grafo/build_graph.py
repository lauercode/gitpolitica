#!/usr/bin/env python3
"""
build_graph.py — gera o grafo de relações a partir do repositório de
dados do GitPolítica (arquivos <UF>/<slug>.md, um por político).

O que é uma "ligação": dois itens citados na MESMA notícia. Isso não
indica envolvimento nem culpa — por isso cada ligação carrega as
notícias que a sustentam.

Fontes de itens:
  - políticos: os próprios arquivos do repositório (ligação político↔
    político = mesma notícia/link em dois arquivos);
  - órgãos, partidos, casos, empresas e pessoas: extraídos do TÍTULO de
    cada notícia por regras locais (sem API). Vai haver ruído: os
    limites --min-news/--min-link e o arquivo entidades_curadas.json
    existem para controlá-lo.

Uso:
    python3 build_graph.py --repo ../data/repo --out site_grafo
    python3 build_graph.py --repo amostra --out /tmp/saida --min-news 2 --min-link 1
"""

import argparse
import json
import os
import re
import unicodedata
from collections import defaultdict
from itertools import combinations

ENTRY = re.compile(
    r"- \*\*\[(?P<d>[^\]]+)\]\*\* (?P<h>.+?)\n  _fonte: \[(?P<s>[^\]]+)\]\((?P<u>[^)]+)\)_"
)
CAP = r"[A-ZÀ-Ý][a-zà-ÿ]+"
SEQ = re.compile(rf"{CAP}(?:\s+(?:d[aeo]s?\s+)?{CAP}){{1,2}}")
EDGE = r"(?<![\wÀ-ÿ])(?:{})(?![\wÀ-ÿ])"

ORGAOS = {
    "STF": "STF", "Supremo Tribunal Federal": "STF", "PF": "Polícia Federal",
    "Polícia Federal": "Polícia Federal", "PGR": "PGR", "TSE": "TSE",
    "Tribunal Superior Eleitoral": "TSE", "TCU": "TCU", "MPF": "MPF",
    "CGU": "CGU", "CNJ": "CNJ", "Banco Central": "Banco Central",
    "Receita Federal": "Receita Federal", "Câmara dos Deputados": "Câmara dos Deputados",
    "Senado Federal": "Senado Federal", "Congresso Nacional": "Congresso Nacional",
}
PARTIDOS = ["PT", "PL", "PSD", "MDB", "PP", "PSB", "PDT", "PSDB", "PSOL", "PCdoB",
            "PRD", "PV", "PSTU", "PCO", "PRTB", "União Brasil", "Republicanos", "Solidariedade"]
EMPRESAS_FIXAS = ["Petrobras", "Vale", "Ambev", "JBS", "Odebrecht", "Braskem", "Eletrobras",
                  "Itaú", "Bradesco", "Banco do Brasil", "Caixa Econômica Federal"]
CASO = re.compile(
    rf"(?:Operação|Caso|CPM?I\s+d[aeo]s?|Escândalo\s+d[aeo]s?)\s+{CAP}(?:\s+{CAP}){{0,2}}"
    r"|Lava Jato|Mensalão|Petrolão"
)
EMPRESA = re.compile(
    rf"(?:Banco|Grupo|Construtora|Empresa|Frigorífico|Mineradora|Companhia)\s+{CAP}(?:\s+{CAP})?"
    rf"|{CAP}(?:\s+{CAP})?\s+(?:S\.A\.|S/A|Ltda\.?)"
)
PARTIDO_GENERICO = re.compile(rf"Partido\s+{CAP}(?:\s+{CAP})?")
TITULOS = re.compile(
    r"^(?:Deputad[oa]|Senador[a]?|Governador[a]?|Presidente|Ministr[oa]|Prefeit[oa]|Vereador[a]?|Dr\.?|Dra\.?)\s+")
# Palavras que iniciam sequências capitalizadas que NÃO são pessoas.
NAO_PESSOA = {"Defesa", "Justiça", "Polícia", "Governo", "Ministério", "São", "Santa", "Nossa", "Estados",
              "Banco", "Grupo", "Veja", "Entenda", "Saiba", "Quem", "Como", "Por", "Para", "Copa", "Festa",
              "Jornal", "Rede", "Portal", "Revista", "Campanha", "Bolsa", "Programa", "Rio", "Boa", "Porto",
              "Foz", "Belo", "Campo", "Nova", "Novo", "Dark", "El", "Fernando"}
IGNORAR_PADRAO = {"Quaest", "Datafolha", "Ipec", "AtlasIntel", "Ibope", "Agência Brasil", "Folha", "Globo"}


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def load_curadas(path):
    cfg = {"ignorar": [], "juntar": {}, "tipos": {}, "adicionar": []}
    if path and os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            cfg.update({k: v for k, v in json.load(f).items() if k in cfg})
    cfg["_ignorar"] = {norm(x) for x in IGNORAR_PADRAO | set(cfg["ignorar"])}
    cfg["_variante"] = {norm(v): canon for canon, vs in cfg["juntar"].items() for v in vs}
    return cfg


def read_repo(repo):
    pols, news = {}, {}
    for root, dirs, files in os.walk(repo):
        dirs[:] = [d for d in dirs if d not in ("_meta", "_nao_reconhecidos", ".git")]
        for fn in files:
            if not fn.endswith(".md"):
                continue
            with open(os.path.join(root, fn), encoding="utf-8") as f:
                text = f.read()
            slug = fn[:-3]
            m = re.match(r"# (.+)", text)
            entries = list(ENTRY.finditer(text))
            pols[slug] = {"name": m.group(1).strip() if m else slug, "total": len(entries)}
            for e in entries:
                n = news.setdefault(e["u"], {"h": e["h"], "d": e["d"][:10], "s": e["s"], "u": e["u"], "pols": set()})
                n["pols"].add(slug)
    return pols, news


def extract(headline, cfg, pol_names):
    """Devolve {(nome, tipo)} extraído do título. Casos > empresas > órgãos > partidos > pessoas."""
    found, text = set(), headline

    def take(rx, tipo, canon=lambda x: x):
        nonlocal text
        for m in rx.finditer(text):
            found.add((canon(m.group(0).strip()), tipo))
        text = rx.sub(lambda m: " " * len(m.group(0)), text)

    take(CASO, "escandalo")
    take(EMPRESA, "empresa")
    take(re.compile(EDGE.format("|".join(re.escape(x) for x in EMPRESAS_FIXAS))), "empresa")
    take(re.compile(EDGE.format("|".join(re.escape(k) for k in sorted(ORGAOS, key=len, reverse=True)))),
         "orgao", lambda x: ORGAOS[x])
    take(re.compile(EDGE.format("|".join(re.escape(x) for x in sorted(PARTIDOS, key=len, reverse=True)))), "partido")
    take(PARTIDO_GENERICO, "partido")
    for item in cfg["adicionar"]:
        for alias in [item["nome"], *item.get("apelidos", [])]:
            if re.search(EDGE.format(re.escape(alias)), headline):
                found.add((item["nome"], item["tipo"]))
    for m in SEQ.finditer(text):
        seq = TITULOS.sub("", m.group(0).strip())
        first = seq.split()[0]
        if first in NAO_PESSOA or len(seq.split()) < 2 or norm(seq) in pol_names:
            continue
        found.add((seq, "pessoa"))
    return found


def curate(name, tipo, cfg):
    name = cfg["_variante"].get(norm(name), name)
    if norm(name) in cfg["_ignorar"]:
        return None
    return name, cfg["tipos"].get(name, tipo)


def build(repo, cfg, min_news, min_link, max_part, top, fotos):
    pols, news = read_repo(repo)
    pol_names = {norm(p["name"]) for p in pols.values()}
    ent_news = defaultdict(set)
    for u, n in news.items():
        n["ents"] = set()
        for name, tipo in extract(n["h"], cfg, pol_names):
            c = curate(name, tipo, cfg)
            if c:
                n["ents"].add(c)
                ent_news[c].add(u)
    keep = {e for e, us in ent_news.items() if len(us) >= min_news}

    pairs, skipped = defaultdict(list), 0
    for u, n in news.items():
        parts = [("politico", s) for s in n["pols"]] + [("ent", e) for e in n["ents"] if e in keep]
        if len(parts) < 2:
            continue
        if len(parts) > max_part:
            skipped += 1
            continue
        for a, b in combinations(sorted(parts, key=str), 2):
            pairs[(a, b)].append(u)

    def nid(x):
        return x[1] if x[0] == "politico" else "e-" + norm(x[1][0])

    links = {k: v for k, v in pairs.items() if len(v) >= min_link}
    used = {x for k in links for x in k}
    nodes = {}
    for x in used:
        if x[0] == "politico":
            p = pols[x[1]]
            foto = f"fotos/{x[1]}.jpg" if fotos and os.path.exists(os.path.join(fotos, f"{x[1]}.jpg")) else None
            nodes[nid(x)] = [nid(x), p["name"], "politico", foto, p["total"]]
        else:
            nodes[nid(x)] = [nid(x), x[1][0], x[1][1], None, len(ent_news[x[1]])]
    top_pols = sorted((n for n in nodes.values() if n[2] == "politico"), key=lambda n: -n[4])[:top]
    allowed = {n[0] for n in top_pols}

    out_links, idx, out_news = [], {}, []
    for (a, b), us in sorted(links.items(), key=lambda kv: -len(kv[1])):
        ids = [nid(a), nid(b)]
        if any(nodes[i][2] == "politico" and i not in allowed for i in ids):
            continue
        ev = []
        for u in sorted(us, key=lambda u: news[u]["d"], reverse=True)[:20]:
            if u not in idx:
                idx[u] = len(out_news)
                n = news[u]
                out_news.append([n["h"], n["d"], n["s"], n["u"]])
            ev.append(idx[u])
        out_links.append([ids[0], ids[1], ev])
    linked = {i for l in out_links for i in l[:2]}
    return {"nodes": [n for n in nodes.values() if n[0] in linked], "links": out_links,
            "news": out_news, "stats": {"noticias": len(news), "puladas_por_lista": skipped,
                                        "entidades_candidatas": len(ent_news), "entidades_mantidas": len(keep)}}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--curadas", default=os.path.join(os.path.dirname(__file__), "entidades_curadas.json"))
    ap.add_argument("--template", default=os.path.join(os.path.dirname(__file__), "template.html"))
    ap.add_argument("--fotos", default=None, help="pasta com <slug>.jpg (miniaturas)")
    ap.add_argument("--min-news", type=int, default=3, help="notícias mínimas para um item virar bloco")
    ap.add_argument("--min-link", type=int, default=2, help="notícias em comum mínimas para uma ligação")
    ap.add_argument("--max-part", type=int, default=10, help="ignora notícias com mais participantes (listas/pesquisas)")
    ap.add_argument("--top", type=int, default=100, help="máximo de políticos")
    a = ap.parse_args()

    g = build(a.repo, load_curadas(a.curadas), a.min_news, a.min_link, a.max_part, a.top, a.fotos)
    os.makedirs(a.out, exist_ok=True)
    with open(os.path.join(a.out, "graph.json"), "w", encoding="utf-8") as f:
        json.dump(g, f, ensure_ascii=False)
    data = "const NEWS={};const NODES={};const LINKS={};".format(
        *(json.dumps(x, ensure_ascii=False) for x in (g["news"], g["nodes"], g["links"])))
    with open(a.template, encoding="utf-8") as f:
        html = f.read().replace("/*DATA*/", data)
    with open(os.path.join(a.out, "index.html"), "w", encoding="utf-8") as f:
        f.write(html)

    tipos = defaultdict(int)
    for n in g["nodes"]:
        tipos[n[2]] += 1
    print(f"{len(g['nodes'])} blocos {dict(tipos)} · {len(g['links'])} ligações · {len(g['news'])} notícias como prova")
    print("estatísticas:", g["stats"])
    top = sorted((n for n in g["nodes"] if n[2] != "politico"), key=lambda n: -n[4])[:30]
    print("itens mais frequentes (revise e alimente entidades_curadas.json):")
    for n in top:
        print(f"  {n[4]:>4}  {n[2]:<10} {n[1]}")


if __name__ == "__main__":
    main()
