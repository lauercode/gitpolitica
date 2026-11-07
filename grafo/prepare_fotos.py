#!/usr/bin/env python3
"""
prepare_fotos.py — associa as fotos de candidatos do TSE (ZIPs por UF
baixados do portal de dados abertos) aos políticos do grafo e gera
miniaturas quadradas `<slug>.jpg`.

Como a associação funciona: o nome de cada arquivo de foto contém o
SQ_CANDIDATO (número de ~12 dígitos, ex.: FSP250001234567_div.jpg), que o
GitPolítica já guarda como `tse_sequencial` em _meta/politicians_tse.json.
O script pega a maior sequência de dígitos do nome do arquivo e procura
esse número no JSON. Só processa os políticos que estão no grafo
(graph.json), para não gerar fotos que o site não usa.

Políticos que são parlamentares EM EXERCÍCIO e também candidatos não têm
`tse_sequencial` no próprio registro (a candidatura foi mesclada na
entrada de mandato), então o script também tenta casar pelo nome (+ UF).

Fotos do TSE: licença CC BY — o site já credita o TSE no cabeçalho.

Uso:
    python3 build_graph.py --repo ../data/repo --out site_grafo
    python3 prepare_fotos.py --graph site_grafo/graph.json --repo ../data/repo \
        --origem D:/fotos_tse --saida site_grafo/fotos
    python3 build_graph.py --repo ../data/repo --out site_grafo --fotos site_grafo/fotos
"""

import argparse
import io
import json
import os
import re
import sys
import unicodedata
import zipfile

TAMANHO = 240
IMG_EXT = (".jpg", ".jpeg", ".png")


def norm(s):
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


def seq_do_arquivo(nome):
    """Maior sequência de dígitos do nome do arquivo (o SQ_CANDIDATO)."""
    runs = re.findall(r"\d{8,}", os.path.basename(nome))
    return max(runs, key=len) if runs else None


def indexar_fotos(origem):
    """{sq: ('arquivo'|'zip', caminho, membro)} sem ler o conteúdo das imagens."""
    idx = {}
    for root, _, files in os.walk(origem):
        for fn in files:
            path = os.path.join(root, fn)
            if fn.lower().endswith(".zip"):
                with zipfile.ZipFile(path) as z:
                    for m in z.namelist():
                        if m.lower().endswith(IMG_EXT) and (sq := seq_do_arquivo(m)):
                            idx[sq] = ("zip", path, m)
            elif fn.lower().endswith(IMG_EXT) and (sq := seq_do_arquivo(fn)):
                idx[sq] = ("arquivo", path, None)
    return idx


def ler_bytes(ref):
    tipo, path, membro = ref
    if tipo == "arquivo":
        with open(path, "rb") as f:
            return f.read()
    with zipfile.ZipFile(path) as z:
        return z.read(membro)


def indice_tse(repo):
    """slug->sq, (nome,uf)->{sq}, nome->{sq} a partir de _meta/politicians_tse.json."""
    path = os.path.join(repo, "_meta", "politicians_tse.json")
    with open(path, encoding="utf-8") as f:
        lista = json.load(f)
    por_slug, por_nome_uf, por_nome = {}, {}, {}
    for p in lista:
        sq = p.get("tse_sequencial")
        if not sq:
            continue
        uf = re.search(r"\(([A-Z]{2})\)", p.get("role", ""))
        uf = uf.group(1) if uf else ""
        por_slug[p["slug"]] = str(sq)
        for nome in {p["name"], *p.get("aliases", [])}:
            if " " in nome:
                por_nome_uf.setdefault((norm(nome), uf), set()).add(str(sq))
                por_nome.setdefault(norm(nome), set()).add(str(sq))
    return por_slug, por_nome_uf, por_nome


def arquivos_do_repo(repo):
    """slug -> (nome do cabeçalho, UF da pasta)."""
    out = {}
    for root, dirs, files in os.walk(repo):
        dirs[:] = [d for d in dirs if d not in ("_meta", "_nao_reconhecidos", ".git")]
        for fn in files:
            if fn.endswith(".md"):
                with open(os.path.join(root, fn), encoding="utf-8") as f:
                    m = re.match(r"# (.+)", f.read())
                out[fn[:-3]] = (m.group(1).strip() if m else fn[:-3], os.path.basename(root))
    return out


def achar_sq(slug, nome, uf, por_slug, por_nome_uf, por_nome):
    if slug in por_slug:
        return por_slug[slug], "slug"
    cand = por_nome_uf.get((norm(nome), uf), set())
    if len(cand) == 1:
        return next(iter(cand)), "nome+uf"
    cand = por_nome.get(norm(nome), set())
    if len(cand) == 1:
        return next(iter(cand)), "nome"
    return None, "ambíguo" if cand or por_nome_uf.get((norm(nome), uf)) else "sem candidatura"


def miniatura(dados, destino):
    from PIL import Image, ImageOps
    img = Image.open(io.BytesIO(dados)).convert("RGB")
    # corta quadrado priorizando o topo (rostos ficam na parte de cima do retrato)
    img = ImageOps.fit(img, (TAMANHO, TAMANHO), Image.LANCZOS, centering=(0.5, 0.22))
    img.save(destino, "JPEG", quality=82, optimize=True)


def preparar(graph, repo, origem, saida):
    por_slug, por_nome_uf, por_nome = indice_tse(repo)
    arqs = arquivos_do_repo(repo)
    fotos = indexar_fotos(origem)
    os.makedirs(saida, exist_ok=True)
    res = {"ok": 0, "sem_foto": [], "sem_candidatura": [], "ambiguos": [], "metodos": {}}
    for node in graph["nodes"]:
        if node[2] != "politico":
            continue
        slug = node[0]
        nome, uf = arqs.get(slug, (node[1], ""))
        sq, metodo = achar_sq(slug, nome, uf, por_slug, por_nome_uf, por_nome)
        if not sq:
            res["ambiguos" if metodo == "ambíguo" else "sem_candidatura"].append(nome)
            continue
        if sq not in fotos:
            res["sem_foto"].append(nome)
            continue
        miniatura(ler_bytes(fotos[sq]), os.path.join(saida, f"{slug}.jpg"))
        res["ok"] += 1
        res["metodos"][metodo] = res["metodos"].get(metodo, 0) + 1
    res["fotos_indexadas"] = len(fotos)
    return res


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--graph", required=True, help="graph.json gerado pelo build_graph.py")
    ap.add_argument("--repo", required=True, help="repositório de dados (com _meta/politicians_tse.json)")
    ap.add_argument("--origem", required=True, help="pasta com os ZIPs/JPGs baixados do TSE")
    ap.add_argument("--saida", required=True, help="pasta das miniaturas (ex.: site_grafo/fotos)")
    a = ap.parse_args()
    try:
        import PIL  # noqa: F401
    except ImportError:
        sys.exit("Falta o Pillow. Instale com:  py -m pip install pillow")
    with open(a.graph, encoding="utf-8") as f:
        graph = json.load(f)
    r = preparar(graph, a.repo, a.origem, a.saida)
    print(f"{r['fotos_indexadas']} fotos encontradas na origem · {r['ok']} miniaturas geradas {r['metodos']}")
    for chave, rotulo in (("sem_foto", "candidatura sem foto na origem"),
                          ("sem_candidatura", "sem candidatura em 2026 no JSON do TSE"),
                          ("ambiguos", "nome ambíguo (mais de uma candidatura)")):
        if r[chave]:
            print(f"{len(r[chave])} {rotulo}: {', '.join(r[chave][:15])}{' …' if len(r[chave]) > 15 else ''}")


if __name__ == "__main__":
    main()
