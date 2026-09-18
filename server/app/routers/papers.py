"""文献 CRUD + 列表（搜索/排序/筛选）+ 四个分类维度的 GROUP BY 视图。"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Paper
from ..schemas import PaperIn, PaperOut, PaperUpdate

router = APIRouter(tags=["papers"])

SORTABLE = {"year", "title", "first_author", "corresponding_author", "subject", "created_at", "updated_at"}


@router.get("/papers")
def list_papers(
    q: str | None = None,
    sort_by: str = "created_at",
    order: str = "desc",
    subject: str | None = None,
    first_author: str | None = None,
    corresponding_author: str | None = None,
    year_from: int | None = None,
    year_to: int | None = None,
    offset: int = 0,
    limit: int = Query(default=50, le=500),
    db: Session = Depends(get_db),
):
    stmt = db.query(Paper)
    if q:
        like = f"%{q}%"
        stmt = stmt.filter(or_(
            Paper.title.like(like),
            Paper.journal.like(like),
            Paper.first_author.like(like),
            Paper.corresponding_author.like(like),
        ))
    if subject:
        stmt = stmt.filter(Paper.subject == subject)
    if first_author:
        stmt = stmt.filter(Paper.first_author == first_author)
    if corresponding_author:
        stmt = stmt.filter(Paper.corresponding_author == corresponding_author)
    if year_from is not None:
        stmt = stmt.filter(Paper.year >= year_from)
    if year_to is not None:
        stmt = stmt.filter(Paper.year <= year_to)

    col = getattr(Paper, sort_by) if sort_by in SORTABLE else Paper.created_at
    stmt = stmt.order_by(col.desc() if order == "desc" else col.asc())
    total = stmt.count()
    rows = stmt.offset(offset).limit(limit).all()
    return {"code": 0, "data": {"total": total, "items": [PaperOut.model_validate(p) for p in rows]}}


@router.post("/papers", status_code=201)
def create_paper(body: PaperIn, db: Session = Depends(get_db)):
    data = body.model_dump()
    if data.get("doi") and db.query(Paper).filter(Paper.doi == data["doi"]).first():
        raise HTTPException(409, "DOI 已存在")
    paper = Paper(**data)
    db.add(paper)
    db.commit()
    db.refresh(paper)
    return {"code": 0, "data": PaperOut.model_validate(paper)}


# 分类 GROUP BY 视图。注意：必须注册在 /papers/{paper_id} 之前，否则 "groups" 会被当 paper_id 解析。
GROUP_DIMS = {
    "year": Paper.year,
    "subject": Paper.subject,
    "first_author": Paper.first_author,
    "corresponding_author": Paper.corresponding_author,
}


@router.get("/papers/groups/{dimension}")
def paper_groups(dimension: str, db: Session = Depends(get_db)):
    if dimension not in GROUP_DIMS:
        raise HTTPException(404, "未知分类维度")
    col = GROUP_DIMS[dimension]
    rows = db.query(col, func.count(Paper.id)).group_by(col).all()
    groups = [{"key": k, "label": str(k) if k is not None else "未分类", "count": c} for k, c in rows]
    if dimension == "year":
        groups.sort(key=lambda g: (g["key"] is not None, g["key"] or 0), reverse=True)   # 未分类置底
    else:
        groups.sort(key=lambda g: (-g["count"], g["label"]))
    return {"code": 0, "data": {"dimension": dimension, "groups": groups}}


@router.get("/papers/{paper_id}")
def get_paper(paper_id: int, db: Session = Depends(get_db)):
    paper = db.get(Paper, paper_id)
    if not paper:
        raise HTTPException(404, "文献不存在")
    return {"code": 0, "data": PaperOut.model_validate(paper)}


@router.put("/papers/{paper_id}")
def update_paper(paper_id: int, body: PaperUpdate, db: Session = Depends(get_db)):
    paper = db.get(Paper, paper_id)
    if not paper:
        raise HTTPException(404, "文献不存在")
    data = body.model_dump(exclude_unset=True)
    if data.get("doi") and data["doi"] != paper.doi:
        if db.query(Paper).filter(Paper.doi == data["doi"]).first():
            raise HTTPException(409, "DOI 已存在")
    for k, v in data.items():
        setattr(paper, k, v)
    db.commit()
    db.refresh(paper)
    return {"code": 0, "data": PaperOut.model_validate(paper)}


@router.delete("/papers/{paper_id}")
def delete_paper(paper_id: int, db: Session = Depends(get_db)):
    """删除文献：数据库记录（批注/补充材料级联）+ 磁盘上的 PDF 原件与渲染缓存。"""
    from pathlib import Path
    from ..config import CACHE_DIR
    from ..models import Supplement

    paper = db.get(Paper, paper_id)
    if not paper:
        raise HTTPException(404, "文献不存在")

    # 收集磁盘文件：正文 + 补充材料 + 对应渲染缓存
    disk_files = [Path(p) for p in [paper.pdf_path] if p]
    supp_ids = []
    for s in db.query(Supplement).filter(Supplement.paper_id == paper_id).all():
        disk_files.append(Path(s.pdf_path))
        supp_ids.append(s.id)
    cache_patterns = [f"p{paper_id}_*"] + [f"s{sid}_*" for sid in supp_ids]
    for pattern in cache_patterns:
        disk_files.extend(CACHE_DIR.glob(pattern))

    db.delete(paper)
    db.commit()

    for f in disk_files:
        f.unlink(missing_ok=True)
    return {"code": 0, "data": {"deleted": paper_id, "files_removed": len(disk_files)}}
