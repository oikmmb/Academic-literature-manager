"""笔记/高亮：批量幂等保存（自动保存核心）+ 单条修改/删除 + 按文献读取。"""
import json

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Annotation, Paper
from ..schemas import AnnotationIn, AnnotationOut, AnnotationPatch, BatchIn

router = APIRouter(tags=["annotations"])


def _deserialize(a: Annotation) -> AnnotationOut:
    return AnnotationOut.model_validate(a)   # segments 由 validator 自动 parse


@router.get("/papers/{paper_id}/annotations")
def list_annotations(
    paper_id: int,
    page: int | None = Query(default=None),
    supp_id: int = Query(default=0),
    db: Session = Depends(get_db),
):
    """supp_id=0 为正文批注；>0 为对应补充材料的批注。"""
    if not db.get(Paper, paper_id):
        raise HTTPException(404, "文献不存在")
    stmt = db.query(Annotation).filter(Annotation.paper_id == paper_id, Annotation.supp_id == supp_id)
    if page is not None:
        stmt = stmt.filter(Annotation.page == page)
    rows = stmt.order_by(Annotation.page, Annotation.created_at).all()
    return {"code": 0, "data": {"items": [_deserialize(a) for a in rows]}}


@router.post("/annotations/batch")
def batch_save(body: BatchIn, db: Session = Depends(get_db)):
    """upsert 幂等：id 为客户端 uuid，重复提交覆盖更新。deletes 为 id 列表。"""
    saved = 0
    for item in body.upserts:
        data = item.model_dump(exclude={"client_id"})
        data["segments"] = json.dumps(data["segments"], ensure_ascii=False) if data.get("segments") else None
        existing = db.get(Annotation, item.client_id)
        if existing:
            for k, v in data.items():
                if k == "paper_id":
                    continue
                setattr(existing, k, v)
        else:
            db.add(Annotation(id=item.client_id, **data))
        saved += 1
    deleted = 0
    for ann_id in body.deletes:
        row = db.get(Annotation, ann_id)
        if row:
            db.delete(row)
            deleted += 1
    db.commit()
    return {"code": 0, "data": {"saved": saved, "deleted": deleted}}


@router.put("/annotations/{ann_id}")
def update_annotation(ann_id: str, body: AnnotationPatch, db: Session = Depends(get_db)):
    ann = db.get(Annotation, ann_id)
    if not ann:
        raise HTTPException(404, "批注不存在")
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(ann, k, v)
    db.commit()
    db.refresh(ann)
    return {"code": 0, "data": AnnotationOut.model_validate(ann)}


@router.delete("/annotations/{ann_id}")
def delete_annotation(ann_id: str, db: Session = Depends(get_db)):
    ann = db.get(Annotation, ann_id)
    if not ann:
        raise HTTPException(404, "批注不存在")
    db.delete(ann)
    db.commit()
    return {"code": 0, "data": {"deleted": ann_id}}
