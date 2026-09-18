"""阅读器：页渲染 PNG 缓存 + 词级数据。"""
import io

import fitz

from app.config import CACHE_DIR



def _import_pdf(client) -> int:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Hello world, this is a test.")
    page.insert_text((72, 100), "Second line of text.")
    buf = io.BytesIO()
    doc.save(buf)
    doc.close()
    r = client.post("/api/v1/import", files={"file": ("t.pdf", buf.getvalue(), "application/pdf")})
    draft = r.json()["data"]
    r = client.post(f"/api/v1/import/{draft['draft_id']}/confirm",
                    json={"title": "Test Paper", "year": 2024})
    return r.json()["data"]["paper"]["id"]


def test_words_endpoint(client):
    pid = _import_pdf(client)
    r = client.get(f"/api/v1/papers/{pid}/pages/1/words")
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["page"] == 1 and data["page_count"] == 1
    assert len(data["words"]) >= 8
    joined = " ".join(w["t"] for w in data["words"])
    assert "Hello" in joined
    w0 = data["words"][0]
    assert {"i", "t", "x", "y", "w", "h", "b", "l"} <= set(w0.keys())


def test_pages_meta_endpoint(client):
    """多页 PDF 的每页尺寸（前端据此创建全部占位容器）。"""
    doc = fitz.open()
    for _ in range(3):
        doc.new_page()
    buf = io.BytesIO()
    doc.save(buf)
    doc.close()
    r = client.post("/api/v1/import", files={"file": ("m.pdf", buf.getvalue(), "application/pdf")})
    draft = r.json()["data"]
    r = client.post(f"/api/v1/import/{draft['draft_id']}/confirm", json={"title": "Multi Page"})
    pid = r.json()["data"]["paper"]["id"]

    r = client.get(f"/api/v1/papers/{pid}/pages/meta")
    assert r.status_code == 200
    pages = r.json()["data"]["pages"]
    assert len(pages) == 3
    assert [p["page"] for p in pages] == [1, 2, 3]
    assert all(p["w"] > 0 and p["h"] > 0 for p in pages)
    # "meta" 不会被误解析为页码
    assert client.get(f"/api/v1/papers/{pid}/pages/meta").status_code == 200


def test_words_page_out_of_range(client):
    pid = _import_pdf(client)
    assert client.get(f"/api/v1/papers/{pid}/pages/9/words").status_code == 404


def test_image_endpoint_and_cache(client):
    pid = _import_pdf(client)
    r = client.get(f"/api/v1/papers/{pid}/pages/1/image")
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/png"
    # 磁盘缓存已生成（键含 PDF 内容指纹）
    cached_files = list(CACHE_DIR.glob(f"p{pid}_*_1@150.png"))
    assert len(cached_files) == 1 and cached_files[0].exists()


def test_image_dpi_levels(client):
    """清晰度档位：300dpi 渲染缓存独立；非法 dpi 400。"""
    pid = _import_pdf(client)
    r = client.get(f"/api/v1/papers/{pid}/pages/1/image", params={"dpi": 300})
    assert r.status_code == 200 and r.headers["content-type"] == "image/png"
    assert list(CACHE_DIR.glob(f"p{pid}_*_1@300.png"))
    r = client.get(f"/api/v1/papers/{pid}/pages/1/image", params={"dpi": 600})
    assert r.status_code == 200
    assert list(CACHE_DIR.glob(f"p{pid}_*_1@600.png"))
    assert client.get(f"/api/v1/papers/{pid}/pages/1/image", params={"dpi": 200}).status_code == 400


def test_reader_needs_pdf(client):
    r = client.post("/api/v1/papers", json={"title": "No PDF"})
    pid = r.json()["data"]["id"]
    assert client.get(f"/api/v1/papers/{pid}/pages/1/words").status_code == 400
    assert client.get(f"/api/v1/papers/{pid}/pages/1/image").status_code == 400
