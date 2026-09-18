"""补充材料：一篇文献可挂多个（SI PDF / 附录等），上传即建记录。"""
import shutil
import uuid

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from sqlalchemy.orm import Session

from ..config import PDF_DIR
from ..db import get_db
from ..models import Paper, Supplement
from ..schemas import SupplementOut
from ..services.pdf import extract_metadata, get_pdf_dir, pdf_hash

router = APIRouter(tags=["supplements"])


@router.get("/papers/{paper_id}/supplements")
def list_supplements(paper_id: int, db: Session = Depends(get_db)):
    if not db.get(Paper, paper_id):
        raise HTTPException(404, "文献不存在")
    rows = db.query(Supplement).filter(Supplement.paper_id == paper_id).order_by(Supplement.id).all()
    return {"code": 0, "data": {"items": [SupplementOut.model_validate(s) for s in rows]}}


@router.post("/papers/{paper_id}/supplements", status_code=201)
async def add_supplement(paper_id: int, file: UploadFile, label: str | None = None, db: Session = Depends(get_db)):
    if not db.get(Paper, paper_id):
        raise HTTPException(404, "文献不存在")
    if not (file.filename or "").lower().endswith(".pdf"):
        raise HTTPException(400, "仅支持 PDF 文件")
    pdf_dir = get_pdf_dir(db)
    pdf_dir.mkdir(parents=True, exist_ok=True)
    filename = f"supp_{uuid.uuid4().hex[:12]}.pdf"
    dest = pdf_dir / filename
    with dest.open("wb") as out:
        shutil.copyfileobj(file.file, out)
    try:
        meta = extract_metadata(dest)
        pages = meta["page_count"]
    except Exception:
        dest.unlink(missing_ok=True)
        raise HTTPException(400, "无法解析该 PDF 文件")

    supp = Supplement(
        paper_id=paper_id,
        label=(label or "").strip() or "补充材料",
        filename=file.filename or filename,
        pdf_path=str(dest),
        pdf_hash=pdf_hash(dest),
        pdf_pages=pages,
    )
    db.add(supp)
    db.commit()
    db.refresh(supp)
    return {"code": 0, "data": SupplementOut.model_validate(supp)}


@router.delete("/supplements/{supp_id}")
def delete_supplement(supp_id: int, db: Session = Depends(get_db)):
    """删除补充材料：记录 + 其批注 + PDF 文件 + 渲染缓存。"""
    from pathlib import Path
    from ..config import CACHE_DIR
    from ..models import Annotation

    supp = db.get(Supplement, supp_id)
    if not supp:
        raise HTTPException(404, "补充材料不存在")
    # 该补充材料的批注一并删除
    db.query(Annotation).filter(Annotation.supp_id == supp_id).delete()
    disk_files = [Path(supp.pdf_path)] + list(CACHE_DIR.glob(f"s{supp_id}_*"))
    db.delete(supp)
    db.commit()
    for f in disk_files:
        f.unlink(missing_ok=True)
    return {"code": 0, "data": {"deleted": supp_id}}
