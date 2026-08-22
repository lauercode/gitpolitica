"""
scraper.py — busca notícias de feeds RSS e retorna itens normalizados.

Usa apenas a biblioteca padrão do Python (xml.etree + urllib), sem
dependências externas, para manter o MVP leve. Suporta tanto URLs
remotas (produção) quanto arquivos locais (teste/desenvolvimento).
"""

import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from email.utils import parsedate_to_datetime
from datetime import datetime, timezone


@dataclass
class NewsItem:
    title: str
    summary: str
    link: str
    published_at: datetime
    source_name: str

    @property
    def full_text(self) -> str:
        return f"{self.title}. {self.summary}"


def _fetch_raw(url_or_path: str) -> bytes:
    if url_or_path.startswith("http://") or url_or_path.startswith("https://"):
        # Alguns servidores (comum em sites de governo) recusam o
        # User-Agent padrão do urllib ("Python-urllib/3.x"), retornando
        # 403/406 — a exceção é capturada silenciosamente por
        # fetch_all_feeds() e o pipeline segue com 0 notícias, sem dar
        # erro visível. Um User-Agent de navegador evita esse bloqueio.
        req = urllib.request.Request(
            url_or_path,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (compatible; GitPoliticaBot/1.0; "
                    "+https://github.com/lauercode/gitpolitica)"
                ),
                "Accept": "application/rss+xml, application/xml, text/xml, */*",
            },
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.read()
    # caminho local (útil para testes offline)
    with open(url_or_path, "rb") as f:
        return f.read()


def _parse_pubdate(raw: str | None) -> datetime:
    if not raw:
        return datetime.now(timezone.utc)
    try:
        return parsedate_to_datetime(raw)
    except (TypeError, ValueError):
        return datetime.now(timezone.utc)


def fetch_feed(source_name: str, url_or_path: str) -> list[NewsItem]:
    """
    Busca e faz parse de um feed RSS 2.0, retornando uma lista de NewsItem.
    Lança exceção se a fonte estiver inacessível — quem chama decide se
    quer capturar e seguir para a próxima fonte.
    """
    raw = _fetch_raw(url_or_path)
    root = ET.fromstring(raw)

    items = []
    for item in root.findall("./channel/item"):
        title = (item.findtext("title") or "").strip()
        summary = (item.findtext("description") or "").strip()
        link = (item.findtext("link") or "").strip()
        pub_date = _parse_pubdate(item.findtext("pubDate"))

        if title:
            items.append(
                NewsItem(
                    title=title,
                    summary=summary,
                    link=link,
                    published_at=pub_date,
                    source_name=source_name,
                )
            )
    return items


def fetch_all_feeds(sources: list[dict]) -> list[NewsItem]:
    """
    Busca todas as fontes configuradas. Fontes que falharem (fora do ar,
    timeout, etc.) são ignoradas com um aviso, sem derrubar o pipeline.
    """
    all_items = []
    for source in sources:
        try:
            items = fetch_feed(source["name"], source["url"])
            all_items.extend(items)
        except Exception as exc:  # noqa: BLE001 - queremos seguir mesmo se uma fonte falhar
            print(f"[aviso] falha ao buscar {source['name']}: {exc}")
    return all_items
