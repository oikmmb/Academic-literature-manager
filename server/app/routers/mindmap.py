"""全局笔记（思维导图）：每篇文献一棵树。CRUD + AI 生成 + 导入。"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import MindmapNode, Paper
from ..services.mindmap_ai import generate_mindmap

router = APIRouter(tags=["mindmap"])


def _node_out(n: MindmapNode) -> dict:
    return {"id": n.id, "text": n.text, "parent_id": n.parent_id, "position": n.position, "x": n.x, "y": n.y}


def _tree(db: Session, paper_id: int) -> dict:
    """嵌套树；无任何节点时返回空树（前端显示"AI 生成/手动添加"入口）。"""
    rows = db.query(MindmapNode).filter(MindmapNode.paper_id == paper_id).order_by(MindmapNode.position, MindmapNode.id).all()
    if not rows:
        return {"id": None, "text": "", "parent_id": None, "position": 0, "children": []}
    by_parent: dict[int | None, list[MindmapNode]] = {}
    for r in rows:
        by_parent.setdefault(r.parent_id, []).append(r)

    def build(n: MindmapNode) -> dict:
        return {**_node_out(n), "children": [build(c) for c in by_parent.get(n.id, [])]}

    roots = by_parent.get(None, [])
    root = roots[0]
    return build(root)


@router.get("/papers/{paper_id}/mindmap")
def get_mindmap(paper_id: int, db: Session = Depends(get_db)):
    if not db.get(Paper, paper_id):
        raise HTTPException(404, "文献不存在")
    return {"code": 0, "data": {"tree": _tree(db, paper_id)}}


class NodeIn(BaseModel):
    parent_id: int | None = None
    text: str = ""


@router.post("/papers/{paper_id}/mindmap/nodes", status_code=201)
def add_node(paper_id: int, body: NodeIn, db: Session = Depends(get_db)):
    paper = db.get(Paper, paper_id)
    if not paper:
        raise HTTPException(404, "文献不存在")
    if body.parent_id is not None:
        parent = db.get(MindmapNode, body.parent_id)
        if not parent or parent.paper_id != paper_id:
            raise HTTPException(404, "父节点不存在")
    # 同父下位置 = 最大值 + 1
    max_pos = db.query(MindmapNode).filter(MindmapNode.paper_id == paper_id, MindmapNode.parent_id == body.parent_id).count()
    node = MindmapNode(paper_id=paper_id, parent_id=body.parent_id, text=body.text or "新节点", position=max_pos)
    db.add(node)
    db.commit()
    db.refresh(node)
    return {"code": 0, "data": _node_out(node)}


class NodePatch(BaseModel):
    text: str | None = None
    x: float | None = None
    y: float | None = None


@router.put("/mindmap/nodes/{node_id}")
def update_node(node_id: int, body: NodePatch, db: Session = Depends(get_db)):
    node = db.get(MindmapNode, node_id)
    if not node:
        raise HTTPException(404, "节点不存在")
    if body.text is not None:
        node.text = body.text.strip() or node.text
    # 拖拽位置持久化：None 传 x=0 表示重置为自动布局？用 sentinel：x 字段显式传入即更新
    if "x" in body.model_fields_set and "y" in body.model_fields_set:
        node.x = body.x
        node.y = body.y
    db.commit()
    return {"code": 0, "data": _node_out(node)}


@router.delete("/mindmap/nodes/{node_id}")
def delete_node(node_id: int, db: Session = Depends(get_db)):
    """删除节点及其整个子树。"""
    node = db.get(MindmapNode, node_id)
    if not node:
        raise HTTPException(404, "节点不存在")
    # 收集子树（Python 递归，量级小）
    todo = [node_id]
    ids = []
    while todo:
        cur = todo.pop()
        ids.append(cur)
        for child in db.query(MindmapNode).filter(MindmapNode.parent_id == cur).all():
            todo.append(child.id)
    db.query(MindmapNode).filter(MindmapNode.id.in_(ids)).delete(synchronize_session=False)
    db.commit()
    return {"code": 0, "data": {"deleted": len(ids)}}


@router.post("/papers/{paper_id}/mindmap/generate")
def ai_generate(paper_id: int, db: Session = Depends(get_db)):
    """AI 梳理全文生成要点树（不落库，前端预览后导入）。"""
    paper = db.get(Paper, paper_id)
    if not paper:
        raise HTTPException(404, "文献不存在")
    if not paper.pdf_path:
        raise HTTPException(400, "该文献没有 PDF，无法提取全文")
    try:
        result = generate_mindmap(paper_id, paper.pdf_path, db)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception:
        raise HTTPException(502, "AI 生成失败，请稍后重试")
    return {"code": 0, "data": result}


class ImportIn(BaseModel):
    tree: dict
    mode: str = "append"   # append=导入为根下新分支；replace=清空重建


@router.post("/papers/{paper_id}/mindmap/import", status_code=201)
def import_tree(paper_id: int, body: ImportIn, db: Session = Depends(get_db)):
    if not db.get(Paper, paper_id):
        raise HTTPException(404, "文献不存在")
    if body.mode == "replace":
        db.query(MindmapNode).filter(MindmapNode.paper_id == paper_id).delete()
    # 找当前根（append 模式挂根下；无根则以导入树为根）
    root = db.query(MindmapNode).filter(MindmapNode.paper_id == paper_id, MindmapNode.parent_id is None).first()

    def insert(node: dict, parent_id: int | None) -> int:
        position = db.query(MindmapNode).filter(
            MindmapNode.paper_id == paper_id, MindmapNode.parent_id == parent_id,
        ).count()
        n = MindmapNode(paper_id=paper_id, parent_id=parent_id, text=node.get("text", "").strip() or "要点", position=position)
        db.add(n)
        db.flush()
        for child in node.get("children") or []:
            insert(child, n.id)
        return n.id

    if body.mode == "append" and root is not None:
        insert(body.tree, root.id)
    else:
        # 导入树直接作为根（append 但当前无根时）
        insert(body.tree, None)
    db.commit()
    return {"code": 0, "data": {"tree": _tree(db, paper_id)}}
