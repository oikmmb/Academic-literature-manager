"""PDF 导入流程：上传 → 元数据提取 → 确认建文献。用 PyMuPDF 内存生成 PDF，零 fixture 依赖。"""
import io

import fitz

from app.config import PDF_DIR


def make_pdf() -> bytes:
    """生成一篇带元数据和首页文字的 3 页测试 PDF。"""
    doc = fitz.open()
    doc.set_metadata({
        "title": "Deep Residual Learning for Image Recognition",
        "author": "Kaiming He; Xiangyu Zhang",
    })
    for pno in range(3):
        page = doc.new_page()
        page.insert_text((72, 72), "Deep Residual Learning for Image Recognition" if pno == 0 else f"Page {pno + 1} content")
        if pno == 0:
            page.insert_text((72, 100), "doi: 10.1109/CVPR.2016.90")
            page.insert_text((72, 130), "Abstract We present a residual learning framework.")
            page.insert_text((72, 160), "Keywords deep learning")
    buf = io.BytesIO()
    doc.save(buf)
    doc.close()
    return buf.getvalue()


def test_import_full_flow(client):
    r = client.post("/api/v1/import",
                    files={"file": ("resnet.pdf", make_pdf(), "application/pdf")})
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["metadata"]["title"].startswith("Deep Residual")
    assert data["metadata"]["authors"] == ["Kaiming He", "Xiangyu Zhang"]
    assert data["metadata"]["doi"] == "10.1109/CVPR.2016.90"
    assert data["metadata"]["page_count"] == 3
    assert data["metadata"]["abstract"]

    # 确认建文献
    r = client.post(f"/api/v1/import/{data['draft_id']}/confirm", json={
        "title": "Deep Residual Learning for Image Recognition",
        "authors": ["Kaiming He", "Xiangyu Zhang"],
        "first_author": "Kaiming He",
        "subject": "计算机视觉",
        "year": 2016,
        "journal": "CVPR",
        "doi": "10.1109/CVPR.2016.90",
    })
    assert r.status_code == 201, r.text
    paper = r.json()["data"]["paper"]
    assert paper["has_pdf"] is True
    assert paper["pdf_pages"] == 3
    assert paper["source"] == "pdf_import"

    # 本次导入的 PDF 文件已落盘（按 draft_id 精确匹配，避免测试顺序耦合）
    pdfs = list(PDF_DIR.glob(f"{data['draft_id']}*.pdf"))
    assert len(pdfs) == 1 and pdfs[0].exists()


def test_import_reject_non_pdf(client):
    r = client.post("/api/v1/import",
                    files={"file": ("a.txt", b"hello", "text/plain")})
    assert r.status_code == 400


def test_remove_supplement_before_confirm(client):
    """传错文件 → 删除 → 确认导入后错误文件不存在（含磁盘清理）。"""
    files = [
        ("file", ("main.pdf", make_pdf(), "application/pdf")),
        ("supp_files", ("wrong.pdf", make_pdf(), "application/pdf")),
        ("supp_files", ("right.pdf", make_pdf(), "application/pdf")),
    ]
    r = client.post("/api/v1/import", files=files)
    data = r.json()["data"]
    assert len(data["supplements"]) == 2
    wrong_sid = data["supplements"][0]["sid"]

    # 删除第一个（错误文件）
    r = client.delete(f"/api/v1/import/{data['draft_id']}/supplements/{wrong_sid}")
    assert r.status_code == 200
    remaining = r.json()["data"]["supplements"]
    assert len(remaining) == 1 and remaining[0]["sid"] != wrong_sid

    # 确认导入：只有剩余的那个补充材料
    r = client.post(f"/api/v1/import/{data['draft_id']}/confirm", json={"title": "Fixed"})
    assert r.status_code == 201
    supps = r.json()["data"]["supplements"]
    assert len(supps) == 1
    assert "wrong" not in supps[0]["filename"]

    # 被删文件的磁盘文件已清理
    from app.config import PDF_DIR
    remaining_files = list(PDF_DIR.glob("*.pdf"))
    assert not any("wrong" in f.name for f in remaining_files)


def test_confirm_missing_draft(client):
    r = client.post("/api/v1/import/deadbeef/confirm", json={"title": "x"})
    assert r.status_code == 404


def test_import_with_supplements(client):
    """正文 + 补充材料一起导入；确认后补充材料可列出、可删除。"""
    files = [
        ("file", ("main.pdf", make_pdf(), "application/pdf")),
        ("supp_files", ("si_1.pdf", make_pdf(), "application/pdf")),
        ("supp_files", ("si_2.pdf", make_pdf(), "application/pdf")),
    ]
    r = client.post("/api/v1/import", files=files)
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert len(data["supplements"]) == 2

    r = client.post(f"/api/v1/import/{data['draft_id']}/confirm", json={"title": "With SI"})
    assert r.status_code == 201, r.text
    body = r.json()["data"]
    pid = body["paper"]["id"]
    assert len(body["supplements"]) == 2
    assert body["supplements"][0]["pdf_pages"] == 3

    # 列出 + 阅读接口支持 supp doc
    r = client.get(f"/api/v1/papers/{pid}/supplements")
    items = r.json()["data"]["items"]
    assert len(items) == 2
    supp_id = items[0]["id"]
    r = client.get(f"/api/v1/papers/{pid}/pages/1/words", params={"doc": f"supp:{supp_id}"})
    assert r.status_code == 200 and len(r.json()["data"]["words"]) >= 8

    # 补充材料批注与正文隔离
    client.post("/api/v1/annotations/batch", json={"upserts": [{
        "client_id": "si-ann-1", "paper_id": pid, "supp_id": supp_id, "page": 1,
        "word_start": 0, "word_end": 2, "text": "si text", "kind": "highlight",
    }]})
    assert len(client.get(f"/api/v1/papers/{pid}/annotations").json()["data"]["items"]) == 0
    assert len(client.get(f"/api/v1/papers/{pid}/annotations", params={"supp_id": supp_id}).json()["data"]["items"]) == 1

    # 删除补充材料：记录 + 其批注一并清理
    from app.config import PDF_DIR
    pdfs_before = len(list(PDF_DIR.glob("*.pdf")))
    assert client.delete(f"/api/v1/supplements/{supp_id}").status_code == 200
    assert len(client.get(f"/api/v1/papers/{pid}/supplements").json()["data"]["items"]) == 1
    assert client.get(f"/api/v1/papers/{pid}/annotations", params={"supp_id": supp_id}).json()["data"]["items"] == []
    # 磁盘文件已清理（删除前后对比，避免测试顺序耦合）
    assert len(list(PDF_DIR.glob("*.pdf"))) == pdfs_before - 1
    assert client.get(f"/api/v1/papers/{pid}/pages/1/words", params={"doc": f"supp:{supp_id}"}).status_code == 404
