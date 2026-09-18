"""papers CRUD + 搜索排序筛选。"""


def _make(client, **overrides):
    body = {
        "title": "Attention Is All You Need",
        "authors": ["Ashish Vaswani", "Noam Shazeer"],
        "first_author": "Ashish Vaswani",
        "corresponding_author": "Noam Shazeer",
        "subject": "深度学习",
        "journal": "NeurIPS",
        "year": 2017,
        "doi": "10.5555/attention2017",
        "source": "manual",
    }
    body.update(overrides)
    r = client.post("/api/v1/papers", json=body)
    assert r.status_code == 201, r.text
    return r.json()["data"]


def test_create_and_get(client):
    p = _make(client)
    r = client.get(f"/api/v1/papers/{p['id']}")
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["title"] == "Attention Is All You Need"
    assert data["year"] == 2017
    assert data["has_pdf"] is False


def test_create_doi_conflict(client):
    _make(client)
    r = client.post("/api/v1/papers", json={
        "title": "dup", "doi": "10.5555/attention2017",
    })
    assert r.status_code == 409


def test_update(client):
    p = _make(client)
    r = client.put(f"/api/v1/papers/{p['id']}", json={"subject": "NLP", "year": 2018})
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["subject"] == "NLP" and data["year"] == 2018
    # 未传字段不动
    assert data["title"] == "Attention Is All You Need"


def test_delete(client):
    p = _make(client)
    r = client.delete(f"/api/v1/papers/{p['id']}")
    assert r.status_code == 200
    assert client.get(f"/api/v1/papers/{p['id']}").status_code == 404


def test_delete_cleans_disk_files(client):
    """删除文献时连带清理 PDF 原件、补充材料文件与渲染缓存。"""
    import io
    import fitz
    from app.config import CACHE_DIR, PDF_DIR

    pdfs_before = len(list(PDF_DIR.glob("*.pdf")))

    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "delete me")
    buf = io.BytesIO()
    doc.save(buf)
    doc.close()

    r = client.post("/api/v1/import", files=[
        ("file", ("del.pdf", buf.getvalue(), "application/pdf")),
        ("supp_files", ("del_si.pdf", buf.getvalue(), "application/pdf")),
    ])
    draft = r.json()["data"]
    r = client.post(f"/api/v1/import/{draft['draft_id']}/confirm", json={"title": "Delete Me"})
    pid = r.json()["data"]["paper"]["id"]
    # 产生渲染缓存
    client.get(f"/api/v1/papers/{pid}/pages/1/image")
    assert len(list(CACHE_DIR.glob(f"p{pid}_*_1@150.png"))) >= 1

    r = client.delete(f"/api/v1/papers/{pid}")
    assert r.status_code == 200
    assert r.json()["data"]["files_removed"] >= 3   # 正文 + 补充材料 + 至少一张缓存

    # 磁盘文件已清理（与删除前对比，避免与其他测试的文件耦合）
    assert len(list(PDF_DIR.glob("*.pdf"))) == pdfs_before
    assert not list(CACHE_DIR.glob(f"p{pid}_*_1@150.png"))


def test_list_filters_and_sort(client):
    _make(client, title="AlphaPaper", first_author="Alice", subject="CV", year=2020, doi="10.1/a")
    _make(client, title="BetaPaper", first_author="Bob", subject="NLP", year=2021, doi="10.1/b")
    _make(client, title="GammaPaper", first_author="Alice", subject="CV", year=2022, doi="10.1/c")

    r = client.get("/api/v1/papers", params={"subject": "CV"})
    assert r.json()["data"]["total"] == 2

    r = client.get("/api/v1/papers", params={"first_author": "Alice"})
    assert r.json()["data"]["total"] == 2

    r = client.get("/api/v1/papers", params={"q": "Beta"})
    assert r.json()["data"]["total"] == 1

    r = client.get("/api/v1/papers", params={"year_from": 2021, "year_to": 2022})
    assert r.json()["data"]["total"] == 2

    r = client.get("/api/v1/papers", params={"sort_by": "year", "order": "asc"})
    years = [it["year"] for it in r.json()["data"]["items"]]
    assert years == sorted(years)
