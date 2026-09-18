"""PDF 导入：上传（正文 + 可选补充材料）→ 提取元数据（draft）→ 用户确认 → 建文献。
draft 存内存（单用户会话内）。"""
import shutil
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from sqlalchemy.orm import Session

from ..config import PDF_DIR
from ..db import get_db
from ..models import Paper, Supplement
from ..schemas import PaperIn, PaperOut, SupplementOut
from ..services.pdf import extract_metadata, get_pdf_dir, pdf_hash

router = APIRouter(tags=["imports"])

DRAFTS: dict[str, dict] = {}


def _save_pdf(upload: UploadFile, prefix: str, pdf_dir: Path) -> tuple[str, int]:
    """保存上传的 PDF 到指定目录，返回 (路径, 页数)。"""
    if not (upload.filename or "").lower().endswith(".pdf"):
        raise HTTPException(400, "仅支持 PDF 文件")
    pdf_dir.mkdir(parents=True, exist_ok=True)
    dest = pdf_dir / f"{prefix}_{uuid.uuid4().hex[:12]}.pdf"
    with dest.open("wb") as out:
        shutil.copyfileobj(upload.file, out)
    try:
        pages = extract_metadata(dest)["page_count"]
    except Exception:
        dest.unlink(missing_ok=True)
        raise HTTPException(400, f"无法解析 PDF 文件：{upload.filename}")
    return str(dest), pages


@router.post("/import")
async def import_pdf(file: UploadFile, supp_files: list[UploadFile] | None = None, db: Session = Depends(get_db)):
    draft_id = uuid.uuid4().hex[:16]
    pdf_dir = get_pdf_dir(db)
    path, pages = _save_pdf(file, draft_id, pdf_dir)
    metadata = extract_metadata(path)
    if not metadata["title"]:
        metadata["title"] = file.filename.rsplit(".", 1)[0]

    supps = []
    for s in supp_files or []:
        spath, spages = _save_pdf(s, f"supp_{draft_id}", pdf_dir)
        supps.append({
            "sid": uuid.uuid4().hex[:12],
            "label": (s.filename or "").rsplit(".", 1)[0] or "补充材料",
            "filename": s.filename or "supp.pdf",
            "pdf_path": spath,
            "pdf_hash": pdf_hash(spath),
            "pdf_pages": spages,
        })

    DRAFTS[draft_id] = {
        "pdf_path": path, "pdf_hash": pdf_hash(path), "page_count": pages, "supps": supps,
    }
    return {"code": 0, "data": {
        "draft_id": draft_id, "metadata": metadata,
        "supplements": [{"sid": s["sid"], "label": s["label"], "pdf_pages": s["pdf_pages"]} for s in supps],
    }}


@router.post("/import/{draft_id}/supplements")
async def draft_add_supplement(draft_id: str, file: UploadFile, label: str | None = None, db: Session = Depends(get_db)):
    """导入确认前向 draft 追加补充材料。"""
    draft = DRAFTS.get(draft_id)
    if not draft:
        raise HTTPException(404, "导入草稿不存在或已过期，请重新导入")
    spath, spages = _save_pdf(file, f"supp_{draft_id}", get_pdf_dir(db))
    supp = {
        "sid": uuid.uuid4().hex[:12],
        "label": (label or "").strip() or (file.filename or "supp.pdf").rsplit(".", 1)[0] or "补充材料",
        "filename": file.filename or "supp.pdf",
        "pdf_path": spath,
        "pdf_hash": pdf_hash(spath),
        "pdf_pages": spages,
    }
    draft["supps"].append(supp)
    return {"code": 0, "data": {"supplements": [
        {"sid": s["sid"], "label": s["label"], "pdf_pages": s["pdf_pages"]} for s in draft["supps"]
    ]}}


@router.delete("/import/{draft_id}/supplements/{sid}")
def draft_remove_supplement(draft_id: str, sid: str):
    """前端删除补充材料：同步从 draft 移除并清理磁盘文件，避免 confirm 时误导入。"""
    draft = DRAFTS.get(draft_id)
    if not draft:
        raise HTTPException(404, "导入草稿不存在或已过期，请重新导入")
    for i, s in enumerate(draft["supps"]):
        if s["sid"] == sid:
            from pathlib import Path
            Path(s["pdf_path"]).unlink(missing_ok=True)
            draft["supps"].pop(i)
            break
    return {"code": 0, "data": {"supplements": [
        {"sid": s["sid"], "label": s["label"], "pdf_pages": s["pdf_pages"]} for s in draft["supps"]
    ]}}


@router.post("/import/{draft_id}/confirm", status_code=201)
def confirm_import(draft_id: str, body: PaperIn, db: Session = Depends(get_db)):
    draft = DRAFTS.pop(draft_id, None)
    if not draft:
        raise HTTPException(404, "导入草稿不存在或已过期，请重新导入")
    data = body.model_dump()
    if data.get("doi") and db.query(Paper).filter(Paper.doi == data["doi"]).first():
        raise HTTPException(409, "该 DOI 已在库中")
    data["source"] = "pdf_import"
    paper = Paper(
        **data,
        pdf_path=draft["pdf_path"],
        pdf_hash=draft["pdf_hash"],
        pdf_pages=draft["page_count"],
    )
    db.add(paper)
    db.flush()
    supps = []
    for s in draft["supps"]:
        supp = Supplement(paper_id=paper.id, **{k: v for k, v in s.items() if k != "sid"})
        db.add(supp)
        supps.append(supp)
    db.commit()
    db.refresh(paper)
    return {"code": 0, "data": {
        "paper": PaperOut.model_validate(paper),
        "supplements": [SupplementOut.model_validate(s) for s in supps],
    }}
