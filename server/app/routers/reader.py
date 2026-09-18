"""阅读器：页 PNG 渲染（缓存）+ 词级文本层数据。doc 参数切换正文/补充材料：
    doc=main（默认）→ 正文；doc=supp:{id} → 补充材料。"""
import fitz
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Paper, Supplement
from ..services.pdf import render_page_png, words_for_page

router = APIRouter(tags=["reader"])


def resolve_doc(paper_id: int, doc: str, db: Session) -> tuple[str, str, int, str]:
    """返回 (doc_key, pdf_path, pdf_pages, pdf_hash)。doc_key 用于渲染缓存。"""
    paper = db.get(Paper, paper_id)
    if not paper:
        raise HTTPException(404, "文献不存在")
    if not doc or doc == "main":
        if not paper.pdf_path:
            raise HTTPException(400, "该文献没有正文 PDF")
        return f"p{paper_id}", paper.pdf_path, paper.pdf_pages, paper.pdf_hash or ""
    if doc.startswith("supp:"):
        try:
            supp_id = int(doc.split(":", 1)[1])
        except ValueError:
            raise HTTPException(400, "doc 参数无效")
        supp = db.get(Supplement, supp_id)
        if not supp or supp.paper_id != paper_id:
            raise HTTPException(404, "补充材料不存在")
        return f"s{supp_id}", supp.pdf_path, supp.pdf_pages, supp.pdf_hash or ""
    raise HTTPException(400, "doc 参数无效")


# 注意：meta 必须注册在 /pages/{page}/words 之前，否则 "meta" 会被当 {page:int} 解析
@router.get("/papers/{paper_id}/pages/meta")
def pages_meta(paper_id: int, doc: str = "main", db: Session = Depends(get_db)):
    """每页尺寸（快速遍历，供前端一次性创建全部占位容器，滚动条/跳页位置正确）。"""
    _doc_key, pdf_path, _pages, _hash = resolve_doc(paper_id, doc, db)
    d = fitz.open(pdf_path)
    try:
        pages = [
            {"page": i + 1, "w": round(d[i].rect.width, 2), "h": round(d[i].rect.height, 2)}
            for i in range(d.page_count)
        ]
    finally:
        d.close()
    return {"code": 0, "data": {"pages": pages}}


@router.get("/papers/{paper_id}/pages/{page}/words")
def page_words(paper_id: int, page: int, doc: str = "main", db: Session = Depends(get_db)):
    _doc_key, pdf_path, pdf_pages, _hash = resolve_doc(paper_id, doc, db)
    if not 1 <= page <= pdf_pages:
        raise HTTPException(404, "页码超出范围")
    return {"code": 0, "data": words_for_page(pdf_path, page)}


@router.get("/papers/{paper_id}/pages/{page}/image")
def page_image(paper_id: int, page: int, doc: str = "main", dpi: int = 150, db: Session = Depends(get_db)):
    if dpi not in (150, 300, 600):
        raise HTTPException(400, "dpi 仅支持 150/300/600")
    doc_key, pdf_path, pdf_pages, pdf_hash = resolve_doc(paper_id, doc, db)
    if not 1 <= page <= pdf_pages:
        raise HTTPException(404, "页码超出范围")
    cached = render_page_png(doc_key, page, pdf_path, pdf_hash, dpi)
    return FileResponse(cached, media_type="image/png", headers={"Cache-Control": "max-age=86400"})
