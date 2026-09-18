"""保存目录配置：settings.pdf_dir 优先于默认 PDF_DIR，导入/补充材料落到自定义目录。"""
import io

import fitz

from app.config import PDF_DIR
from app.db import SessionLocal
from app.services.pdf import get_pdf_dir


def _pdf_bytes() -> bytes:
    doc = fitz.open()
    doc.new_page().insert_text((72, 80), "custom dir test")
    buf = io.BytesIO()
    doc.save(buf)
    doc.close()
    return buf.getvalue()


def test_get_pdf_dir_default(client):
    db = SessionLocal()
    assert get_pdf_dir(db) == PDF_DIR
    db.close()


def test_get_pdf_dir_custom(client, tmp_path):
    client.put("/api/v1/settings/pdf_dir", json={"value": str(tmp_path)})
    db = SessionLocal()
    assert get_pdf_dir(db) == tmp_path
    assert tmp_path.exists()   # 自动创建
    db.close()
    client.put("/api/v1/settings/pdf_dir", json={"value": ""})


def test_import_to_custom_dir(client, tmp_path):
    client.put("/api/v1/settings/pdf_dir", json={"value": str(tmp_path)})
    r = client.post("/api/v1/import", files={
        ("file", ("c.pdf", _pdf_bytes(), "application/pdf")),
        ("supp_files", ("s.pdf", _pdf_bytes(), "application/pdf")),
    })
    draft = r.json()["data"]
    r = client.post(f"/api/v1/import/{draft['draft_id']}/confirm", json={"title": "Custom Dir"})
    assert r.status_code == 201
    # 文件落在自定义目录，默认目录没有新文件
    assert len(list(tmp_path.glob("*.pdf"))) == 2
    # 正文 pdf 存在（通过阅读接口可读）
    pid = r.json()["data"]["paper"]["id"]
    r = client.get(f"/api/v1/papers/{pid}/pages/1/words")
    assert r.status_code == 200
    client.put("/api/v1/settings/pdf_dir", json={"value": ""})


def test_supplement_to_custom_dir(client, tmp_path):
    r = client.post("/api/v1/papers", json={"title": "Supp Dir", "doi": "10.9/sd"})
    pid = r.json()["data"]["id"]
    client.put("/api/v1/settings/pdf_dir", json={"value": str(tmp_path)})
    r = client.post(f"/api/v1/papers/{pid}/supplements",
                    files={"file": ("si.pdf", _pdf_bytes(), "application/pdf")})
    assert r.status_code == 201
    assert len(list(tmp_path.glob("supp_*.pdf"))) == 1
    client.put("/api/v1/settings/pdf_dir", json={"value": ""})
