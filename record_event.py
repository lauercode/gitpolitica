"""
record_event.py — interface de linha de comando para registrar, de
forma manual e curada, os dois tipos de evento que git_events.py
modela com mecanismos reais do Git: troca de partido (merge) e marcos
formais (tag anotada).

Por que uma interface manual, e não automática? Ver a explicação no
topo de git_events.py — classificar corretamente esse tipo de evento a
partir de texto livre de notícia é um problema de NLP não trivial, e
um erro aqui reescreveria um fato central sobre o político na "fonte
de verdade" do repositório. O fluxo pensado é: você (ou um humano
revisando) lê a notícia, confirma os detalhes, e roda um dos comandos
abaixo.

Uso:
    # Troca de partido
    python3 record_event.py partido \\
        --slug arthur-lira \\
        --nome "Arthur Lira" \\
        --de PP \\
        --para PSD \\
        --manchete "Anuncia filiação ao PSD em coletiva de imprensa" \\
        --fonte "Agência Câmara - Política" \\
        --url "https://exemplo.com/noticia/123"

    # Marco formal (posse, cassação, condenação, eleição...)
    python3 record_event.py marco \\
        --slug arthur-lira \\
        --tag "v2027.01-posse" \\
        --tag-mensagem "Toma posse para novo mandato" \\
        --manchete "Arthur Lira toma posse como deputado federal" \\
        --fonte "Agência Câmara - Política" \\
        --url "https://exemplo.com/noticia/456"
"""

import argparse
import sys

from config import POLITICIANS
from repo_writer import ensure_repo
from git_events import record_party_change, record_milestone


def _find_politician(slug: str) -> dict | None:
    return next((p for p in POLITICIANS if p["slug"] == slug), None)


def _cmd_partido(args: argparse.Namespace) -> None:
    politician = _find_politician(args.slug)
    if politician is None:
        print(f"Erro: político com slug '{args.slug}' não encontrado em config.py")
        sys.exit(1)

    print(f"Confirmar troca de partido:")
    print(f"  Político: {politician['name']} ({args.slug})")
    print(f"  {args.de} -> {args.para}")
    print(f"  Manchete: {args.manchete}")
    print(f"  Fonte: {args.fonte} ({args.url})")
    resposta = input("Confirma? [s/N] ").strip().lower()
    if resposta != "s":
        print("Cancelado.")
        return

    ensure_repo()
    merge_hash = record_party_change(
        politician=politician,
        old_party=args.de,
        new_party=args.para,
        headline=args.manchete,
        source_name=args.fonte,
        source_url=args.url,
    )
    print(f"Merge criado: {merge_hash[:8]}")


def _cmd_marco(args: argparse.Namespace) -> None:
    politician = _find_politician(args.slug)
    if politician is None:
        print(f"Erro: político com slug '{args.slug}' não encontrado em config.py")
        sys.exit(1)

    print(f"Confirmar marco formal:")
    print(f"  Político: {politician['name']} ({args.slug})")
    print(f"  Tag: {args.tag} — {args.tag_mensagem}")
    print(f"  Manchete: {args.manchete}")
    print(f"  Fonte: {args.fonte} ({args.url})")
    resposta = input("Confirma? [s/N] ").strip().lower()
    if resposta != "s":
        print("Cancelado.")
        return

    ensure_repo()
    commit_hash = record_milestone(
        politician=politician,
        tag_name=args.tag,
        tag_message=args.tag_mensagem,
        headline=args.manchete,
        source_name=args.fonte,
        source_url=args.url,
    )
    print(f"Commit criado: {commit_hash[:8]} (tag '{args.tag}' aponta pra ele)")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="comando", required=True)

    p_partido = subparsers.add_parser("partido", help="registra troca de partido (merge)")
    p_partido.add_argument("--slug", required=True)
    p_partido.add_argument("--nome", required=False, help="(informativo, não usado diretamente)")
    p_partido.add_argument("--de", required=True, help="sigla do partido de origem")
    p_partido.add_argument("--para", required=True, help="sigla do partido de destino")
    p_partido.add_argument("--manchete", required=True)
    p_partido.add_argument("--fonte", required=True)
    p_partido.add_argument("--url", required=True)
    p_partido.set_defaults(func=_cmd_partido)

    p_marco = subparsers.add_parser("marco", help="registra marco formal (tag anotada)")
    p_marco.add_argument("--slug", required=True)
    p_marco.add_argument("--tag", required=True, help="nome da tag, ex: v2027.01-posse")
    p_marco.add_argument("--tag-mensagem", required=True)
    p_marco.add_argument("--manchete", required=True)
    p_marco.add_argument("--fonte", required=True)
    p_marco.add_argument("--url", required=True)
    p_marco.set_defaults(func=_cmd_marco)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
