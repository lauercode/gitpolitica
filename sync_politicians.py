"""
sync_politicians.py — busca a lista completa de deputados e senadores
nas respectivas APIs e salva localmente. config.py lê esses arquivos
automaticamente (se existirem) e mescla com a lista manual de cargos
"especiais" (Presidente, Ministros, Governadores).

Uso:
    python3 sync_politicians.py            # produção, busca das APIs reais
    python3 sync_politicians.py --sample   # offline, usa os arquivos de amostra
"""

import json
import os
import sys

import camara_api
import senado_api

CAMARA_OUTPUT_PATH = "data/politicians_camara.json"
SENADO_OUTPUT_PATH = "data/politicians_senado.json"


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
    _save(politicians, CAMARA_OUTPUT_PATH, "deputados")


def sync_senado(use_sample: bool) -> None:
    if use_sample:
        print("[modo teste] Senado: usando sample_senadores.xml (offline)")
        with open("sample_senadores.xml", "rb") as f:
            records = senado_api.parse_senadores_xml(f.read())
    else:
        print("Buscando senadores na API do Senado...")
        records = senado_api.fetch_all_senadores()

    politicians = senado_api.build_politicians_list(records)
    _save(politicians, SENADO_OUTPUT_PATH, "senadores(as)")


def run(use_sample: bool = False) -> None:
    sync_camara(use_sample)
    print()
    sync_senado(use_sample)


if __name__ == "__main__":
    run(use_sample="--sample" in sys.argv)
