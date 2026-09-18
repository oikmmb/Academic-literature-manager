"""Crossref 查询：DOI 补全元数据 / 标题检索候选（图片匹配补录）。"""
import httpx
from fastapi import APIRouter, HTTPException

from ..services.crossref import lookup_doi, search

router = APIRouter(tags=["crossref"])


@router.get("/crossref/lookup")
def crossref_lookup(doi: str):
    try:
        return {"code": 0, "data": lookup_doi(doi)}
    except httpx.HTTPStatusError as e:
        raise HTTPException(404 if e.response.status_code == 404 else 502, f"Crossref 查询失败 ({e.response.status_code})")
    except httpx.HTTPError:
        raise HTTPException(502, "Crossref 网络请求失败")


@router.get("/crossref/search")
def crossref_search(q: str, rows: int = 5):
    try:
        return {"code": 0, "data": search(q, rows=min(rows, 10))}
    except httpx.HTTPError:
        raise HTTPException(502, "Crossref 网络请求失败")
