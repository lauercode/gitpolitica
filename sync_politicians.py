"""
sync_politicians.py — busca a lista completa de deputados e senadores
nas respectivas APIs e salva DENTRO do repositório de dados
(config.REPO_DIR), commitando o resultado ali. config.py lê esses
arquivos automaticamente (se existirem) e mescla com a lista manual de
cargos "especiais" (Presidente, Ministros, Governadores).

IMPORTANTE: esses arquivos moram dentro de REPO_DIR de propósito — é o
único lugar que persiste de fato entre execuções em produção (checkout
+ push a cada run). Um caminho fora dele seria recriado do zero a cada
execução do CI, e a lista sincronizada se perderia silenciosamente em
toda run que não chamasse este script — foi exatamente esse bug que
motivou esta versão (ver README).

Uso:
    python3 sync_politicians.py            # produção, busca das APIs reais
    python3 sync_politicians.py --sample   # offline, usa os arquivos de amostra
"""

import json
import os
import sys

import camara_api
import senado_api
from config import _CAMARA_PATH, _SENADO_PATH
from repo_writer import ensure_repo, _run_git


def _save(politicians: list[dict], path: str, label: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(politicians, f, ensure_ascii=False, indent=2)

    print(f"{len(politicians)} {label} salvos em {path}")
    for p in politicians[:5]:
        print(f"  - {p['name']} ({p['party']}/{p['slug']})")
    if len(politicians) > 5:
        print(f"  ... e mais {len(politicians) - 5}")


def sync_camara(use_sample: bool) -> None:
    if use_sample:
        print("[modo teste] Câmara: usando sample_deputados.json (offline)")
        with open("sample_deputados.json", encoding="utf-8") as f:
            records = json.load(f)
    else:
        print("Buscando deputados na API da Câmara...")
        records = camara_api.fetch_all_deputados()

    politicians = camara_api.build_politicians_list(records)
    _save(politicians, _CAMARA_PATH, "deputados")


def sync_senado(use_sample: bool) -> None:
    if use_sample:
        print("[modo teste] Senado: usando sample_senadores.xml (offline)")
        with open("sample_senadores.xml", "rb") as f:
            records = senado_api.parse_senadores_xml(f.read())
    else:
        print("Buscando senadores na API do Senado...")
        records = senado_api.fetch_all_senadores()

    politicians = senado_api.build_politicians_list(records)
    _save(politicians, _SENADO_PATH, "senadores(as)")


def _commit_meta_files(repo_dir: str) -> None:
    """
    Commita os JSONs gerados dentro do repositório de dados. Não faz
    nada (sem erro) se não houver mudança desde o último sync — por
    exemplo, se a composição da Câmara/Senado não mudou.
    """
    _run_git(["add", "_meta"], cwd=repo_dir)

    diff = _run_git(["diff", "--cached", "--name-only"], cwd=repo_dir)
    if not diff:
        print("Nenhuma mudança na lista de políticos desde o último sync.")
        return

    _run_git(
        ["commit", "-q", "-m", "chore: sincroniza lista de deputados/senadores"],
        cwd=repo_dir,
    )
    print("Commit da lista sincronizada criado.")


def run(use_sample: bool = False) -> None:
    from config import REPO_DIR

    ensure_repo(REPO_DIR)

    sync_camara(use_sample)
    print()
    sync_senado(use_sample)
    print()
    _commit_meta_files(REPO_DIR)


if __name__ == "__main__":
    run(use_sample="--sample" in sys.argv)
