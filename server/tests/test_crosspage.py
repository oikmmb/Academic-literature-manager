"""跨页选词：页眉页脚 zone 分类 + 多段 segments 锚点保存。"""
import io
import json

import fitz

from app.services.pdf import words_for_page


def _pdf_with_header_footer() -> bytes:
    """页眉（顶部标题行）+ 正文 + 页脚（页码），每页同构。"""
    doc = fitz.open()
    for pno in range(2):
        page = doc.new_page()
        page.insert_text((72, 30), f"Journal of Testing - Vol.1")          # 页眉
        page.insert_text((72, 100), f"Body text line one of page {pno + 1}.")
        page.insert_text((72, 125), f"Body text line two of page {pno + 1}.")
        page.insert_text((72, 150), "More body content here.")
        page.insert_text((300, 780), f"- {pno + 1} -")                     # 页脚页码
    buf = io.BytesIO()
    doc.save(buf)
    doc.close()
    return buf.getvalue()


def test_zone_classification():
    import tempfile
    from pathlib import Path
    tmp = Path(tempfile.mkdtemp()) / "t.pdf"
    tmp.write_bytes(_pdf_with_header_footer())
    data = words_for_page(str(tmp), 1)
    zones = {}
    for w in data["words"]:
        zones.setdefault(w["zone"], []).append(w["t"])
    assert "header" in zones and "Journal" in " ".join(zones["header"])
    assert "footer" in zones and "-" in " ".join(zones["footer"])
    body = " ".join(zones["body"])
    assert "Body text line one" in body
    assert "Journal" not in body and "- 1 -" not in body


def test_crosspage_segments_save_and_read(client):
    r = client.post("/api/v1/import", files={"file": ("c.pdf", _pdf_with_header_footer(), "application/pdf")})
    draft = r.json()["data"]
    r = client.post(f"/api/v1/import/{draft['draft_id']}/confirm", json={"title": "Cross Page"})
    pid = r.json()["data"]["paper"]["id"]

    segments = [
        {"page": 1, "ws": 2, "we": 8},
        {"page": 2, "ws": 0, "we": 5},
    ]
    ann = {
        "client_id": "cross-1", "paper_id": pid, "page": 1,
        "word_start": 2, "word_end": 8, "text": "body text across pages",
        "segments": segments, "color": "#FFEB3B", "kind": "highlight",
    }
    r = client.post("/api/v1/annotations/batch", json={"upserts": [ann]})
    assert r.status_code == 200, r.text
    assert r.json()["data"]["saved"] == 1

    items = client.get(f"/api/v1/papers/{pid}/annotations").json()["data"]["items"]
    assert len(items) == 1
    assert items[0]["segments"] == segments

    # 幂等覆盖不丢 segments
    client.post("/api/v1/annotations/batch", json={"upserts": [{**ann, "note": "note"}]})
    items = client.get(f"/api/v1/papers/{pid}/annotations").json()["data"]["items"]
    assert items[0]["segments"] == segments and items[0]["note"] == "note"

    # 单段（segments 为 null）兼容旧格式
    client.post("/api/v1/annotations/batch", json={"upserts": [{
        "client_id": "single-1", "paper_id": pid, "page": 1,
        "word_start": 0, "word_end": 3, "text": "single", "kind": "highlight",
    }]})
    items = client.get(f"/api/v1/papers/{pid}/annotations").json()["data"]["items"]
    single = next(i for i in items if i["id"] == "single-1")
    assert single["segments"] is None
