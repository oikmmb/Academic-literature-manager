"""数据目录迁移：库中 PDF 绝对路径失效后按文件名在新目录重定位。"""
import shutil

import fitz

from app.config import PDF_DIR
from app.db import SessionLocal
from app.main import _relocate_pdfs
from app.models import Paper


def test_relocate_pdfs(monkeypatch, tmp_path, client):
    # 建一篇带 PDF 的文献
    import io
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "relocate me")
    buf = io.BytesIO()
    doc.save(buf)
    doc.close()
    r = client.post("/api/v1/import", files={"file": ("r.pdf", buf.getvalue(), "application/pdf")})
    draft = r.json()["data"]
    client.post(f"/api/v1/import/{draft['draft_id']}/confirm", json={"title": "Relocate"})

    db = SessionLocal()
    paper = db.query(Paper).first()
    old_path = paper.pdf_path
    db.close()

    # 模拟数据目录整体搬迁：PDF 文件移到新目录，库里路径失效
    new_pdf_dir = tmp_path / "new_pdfs"
    new_pdf_dir.mkdir()
    shutil.move(old_path, new_pdf_dir / old_path.split("\\")[-1])
    monkeypatch.setattr("app.config.PDF_DIR", new_pdf_dir)

    _relocate_pdfs()

    db = SessionLocal()
    paper = db.query(Paper).first()
    db.close()
    assert str(new_pdf_dir) in paper.pdf_path
    import pathlib
    assert pathlib.Path(paper.pdf_path).exists()


def test_relocate_skips_valid_and_missing(client):
    """有效路径不动；目标目录也没有该文件时保持原样（不误改）。"""
    db = SessionLocal()
    db.add(Paper(title="no pdf", pdf_path=None, doi="10.9/no"))
    db.add(Paper(title="missing pdf", pdf_path="Z:/nowhere/ghost.pdf", doi="10.9/ghost"))
    db.commit()
    db.close()
    _relocate_pdfs()
    db = SessionLocal()
    missing = db.query(Paper).filter(Paper.title == "missing pdf").first()
    db.close()
    assert missing.pdf_path == "Z:/nowhere/ghost.pdf"   # 找不到候选时不改
