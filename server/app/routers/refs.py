"""参考文献查询：悬停正文 [N] 引用时返回对应条目。refs 为空时惰性解析。"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Paper, Reference
from ..services.refs import parse_references

router = APIRouter(tags=["references"])


def ensure_references(paper: Paper, db: Session) -> None:
    """该文献未解析过参考文献时惰性解析入库。"""
    has = db.query(Reference).filter(Reference.paper_id == paper.id).first()
    if has is None and paper.pdf_path:
        for num, text in parse_references(paper.pdf_path):
            db.add(Reference(paper_id=paper.id, ref_num=num, text=text))
        db.commit()


@router.get("/papers/{paper_id}/references")
def get_references(
    paper_id: int,
    nums: str = Query(default="", description="逗号分隔的编号，如 88,89,90"),
    db: Session = Depends(get_db),
):
    paper = db.get(Paper, paper_id)
    if not paper:
        raise HTTPException(404, "文献不存在")
    ensure_references(paper, db)
    if not nums.strip():
        total = db.query(Reference).filter(Reference.paper_id == paper_id).count()
        return {"code": 0, "data": {"items": [], "total": total}}
    try:
        wanted = sorted({int(x) for x in nums.split(",") if x.strip()})
    except ValueError:
        raise HTTPException(400, "nums 参数无效")
    wanted = wanted[:20]
    rows = db.query(Reference).filter(
        Reference.paper_id == paper_id, Reference.ref_num.in_(wanted),
    ).all()
    by_num = {r.ref_num: r.text for r in rows}
    items = [{"num": n, "text": by_num.get(n, "")} for n in wanted if by_num.get(n)]
    return {"code": 0, "data": {"items": items, "total": db.query(Reference).filter(Reference.paper_id == paper_id).count()}}
