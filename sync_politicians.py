"""
sync_politicians.py — busca a lista completa de deputados, senadores e
candidatos à eleição de 2026 (TSE) nas respectivas fontes e salva
DENTRO do repositório de dados (config.REPO_DIR), commitando o
resultado ali. config.py lê esses arquivos automaticamente (se
existirem) e mescla com a lista manual de cargos "especiais"
(Presidente, Ministros, Governadores).


IMPORTANTE: esses arquivos moram dentro de REPO_DIR de propósito — é o
único lugar que persiste de fato entre execuções em produção (checkout
+ push a cada run). Um caminho fora dele seria recriado do zero a cada
execução do CI, e a lista sincronizada se perderia silenciosamente em
toda run que não chamasse este script — foi exatamente esse bug que
motivou esta versão (ver README).

⚠️ O sync do TSE baixa e processa um arquivo BEM maior que o da
Câmara/Senado (dezenas de milhares de candidatos em vez de ~600
pessoas) — pode demorar mais nesta etapa. Use --skip-tse para pular
essa parte em testes locais rápidos.

Uso:
    python3 sync_politicians.py               # produção, busca das fontes reais
    python3 sync_politicians.py --sample      # offline, usa os arquivos de amostra
    python3 sync_politicians.py --skip-tse    # pula o sync do TSE (mais rápido)
"""

import json
import os
import sys

import camara_api
import senado_api
import tse_api
from config import _CAMARA_PATH, _SENADO_PATH, _TSE_PATH
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


def sync_tse(use_sample: bool, local_zip_path: str | None = None) -> None:
    if use_sample:
        print("[modo teste] TSE: usando sample_tse_candidatos.csv (offline)")
        import csv
        with open("sample_tse_candidatos.csv", encoding="utf-8") as f:
            reader = csv.DictReader(f, delimiter=";")
            records = tse_api.parse_candidatos_csv(reader)
        politicians = tse_api.build_politicians_list(records)
    else:
        politicians = tse_api.fetch_and_build(local_zip_path=local_zip_path)

    _save(politicians, _TSE_PATH, "candidatos (eleição 2026)")


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
        ["commit", "-q", "-m", "chore: sincroniza lista de deputados/senadores/candidatos"],
        cwd=repo_dir,
    )
    print("Commit da lista sincronizada criado.")


def _run_sync_step(label: str, func, *args, **kwargs) -> None:
    """
    Roda uma etapa de sync isolada de falhas: se essa fonte específica
    falhar (timeout de rede, bloqueio de CDN, etc.), avisa e segue em
    frente, sem derrubar as outras fontes que já tinham funcionado.
    Bug real encontrado em produção: uma falha pontual de timeout na
    API da Câmara derrubava o script inteiro, perdendo também um sync
    de Senado/TSE que já tinha sido concluído com sucesso na mesma run.
    """
    try:
        func(*args, **kwargs)
    except Exception as exc:  # noqa: BLE001
        print(f"[aviso] sync de {label} falhou, pulando essa etapa: {exc}")
    print()


def run(
    use_sample: bool = False,
    skip_tse: bool = False,
    skip_camara: bool = False,
    skip_senado: bool = False,
    tse_local_zip: str | None = None,
) -> None:
    from config import REPO_DIR

    ensure_repo(REPO_DIR)

    if not skip_camara:
        _run_sync_step("Câmara", sync_camara, use_sample)
    if not skip_senado:
        _run_sync_step("Senado", sync_senado, use_sample)
    if not skip_tse:
        _run_sync_step("TSE", sync_tse, use_sample, local_zip_path=tse_local_zip)
    _commit_meta_files(REPO_DIR)


def _get_arg_value(flag: str) -> str | None:
    """Extrai o valor de uma flag no formato --flag=valor de sys.argv."""
    for arg in sys.argv:
        if arg.startswith(f"{flag}="):
            return arg.split("=", 1)[1]
    return None


if __name__ == "__main__":
    run(
        use_sample="--sample" in sys.argv,
        skip_tse="--skip-tse" in sys.argv,
        skip_camara="--skip-camara" in sys.argv,
        skip_senado="--skip-senado" in sys.argv,
        tse_local_zip=_get_arg_value("--tse-arquivo-local"),
    )
