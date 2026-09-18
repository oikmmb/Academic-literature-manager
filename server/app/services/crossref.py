"""Crossref 客户端：DOI 精确查询 + 标题检索（M2 用 lookup，M6 图片补录用 search）。"""
import re

import httpx

API = "https://api.crossref.org"
HEADERS = {"User-Agent": "LitManager/0.1 (local desktop app)"}


def _clean_abstract(raw: str | None) -> str | None:
    if not raw:
        return None
    text = re.sub(r"<[^>]+>", " ", raw)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:3000] or None


def _parse_item(msg: dict) -> dict:
    title = (msg.get("title") or [""])[0]
    authors = []
    for a in msg.get("author", [])[:50]:
        name = f"{a.get('given', '')} {a.get('family', '')}".strip()
        if name:
            authors.append(name)
    issued = (msg.get("issued") or {}).get("date-parts") or [[None]]
    year = issued[0][0] if issued[0] else None
    journal = (msg.get("container-title") or [""])[0] or None
    return {
        "title": title,
        "authors": authors,
        "first_author": authors[0] if authors else None,
        "corresponding_author": None,
        "year": int(year) if year else None,
        "journal": journal,
        "volume": msg.get("volume"),
        "issue": msg.get("issue"),
        "pages": msg.get("page"),
        "doi": msg.get("DOI"),
        "abstract": _clean_abstract(msg.get("abstract")),
        "published_at": None,
    }


def lookup_doi(doi: str) -> dict:
    """按 DOI 查询单篇元数据。抛 httpx.HTTPError 由调用方转 404/502。"""
    resp = httpx.get(f"{API}/works/{doi}", headers=HEADERS, timeout=15)
    resp.raise_for_status()
    return _parse_item(resp.json()["message"])


def search(query: str, rows: int = 5) -> list[dict]:
    """标题/书目检索候选列表（图片匹配未命中时补录用）。"""
    resp = httpx.get(
        f"{API}/works",
        params={"query.bibliographic": query, "rows": rows},
        headers=HEADERS, timeout=15,
    )
    resp.raise_for_status()
    return [_parse_item(it) for it in resp.json()["message"]["items"]]
