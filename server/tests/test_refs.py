"""参考文献：解析（[N] 格式/续行/降级）、查询接口、惰性解析。"""
import io

import fitz

from app.services.refs import parse_references


def _pdf_with_refs() -> bytes:
    doc = fitz.open()
    # 正文页
    p = doc.new_page()
    p.insert_text((72, 100), "We propose a method [1], extended by [2] and [3].")
    # References 页
    p = doc.new_page()
    p.insert_text((72, 80), "References")
    p.insert_text((72, 110), "[1] Vaswani A, Shazeer N. Attention is all you need.")
    p.insert_text((72, 140), "NeurIPS, 2017.")
    p.insert_text((72, 170), "[2] He K, Zhang X. Deep residual learning for image")
    p.insert_text((72, 195), "recognition. CVPR, 2016.")
    p.insert_text((72, 225), "[3] Brown T, Mann B. Language models are few-shot learners. 2020.")
    buf = io.BytesIO()
    doc.save(buf)
    doc.close()
    return buf.getvalue()


def test_parse_references():
    doc = fitz.open(stream=_pdf_with_refs(), filetype="pdf")
    doc.save("/tmp/_t_refs.pdf") if False else None
    import tempfile
    from pathlib import Path
    tmp = Path(tempfile.mkdtemp()) / "t.pdf"
    tmp.write_bytes(_pdf_with_refs())
    entries = parse_references(str(tmp))
    assert len(entries) == 3
    nums = [n for n, _ in entries]
    assert nums == [1, 2, 3]
    assert "Attention is all you need" in entries[0][1]
    assert "NeurIPS" in entries[0][1]          # 续行已并入
    assert "residual learning" in entries[1][1]  # 跨行条目完整


def test_parse_no_references():
    import tempfile
    from pathlib import Path
    doc = fitz.open()
    doc.new_page().insert_text((72, 80), "no refs here")
    buf = io.BytesIO()
    doc.save(buf)
    doc.close()
    tmp = Path(tempfile.mkdtemp()) / "t.pdf"
    tmp.write_bytes(buf.getvalue())
    assert parse_references(str(tmp)) == []


def test_refs_api_and_lazy_parse(client):
    r = client.post("/api/v1/import", files={"file": ("r.pdf", _pdf_with_refs(), "application/pdf")})
    draft = r.json()["data"]
    r = client.post(f"/api/v1/import/{draft['draft_id']}/confirm", json={"title": "Refs Paper"})
    pid = r.json()["data"]["paper"]["id"]

    # 首次查询触发惰性解析
    r = client.get(f"/api/v1/papers/{pid}/references", params={"nums": "1,2,3"})
    assert r.status_code == 200, r.text
    items = {i["num"]: i["text"] for i in r.json()["data"]["items"]}
    assert set(items) == {1, 2, 3}
    assert "Attention" in items[1]
    assert r.json()["data"]["total"] == 3

    # 部分命中
    r = client.get(f"/api/v1/papers/{pid}/references", params={"nums": "2,99"})
    items = r.json()["data"]["items"]
    assert [i["num"] for i in items] == [2]

    # 无效参数
    assert client.get(f"/api/v1/papers/{pid}/references", params={"nums": "abc"}).status_code == 400
    # 文献不存在
    assert client.get("/api/v1/papers/999/references", params={"nums": "1"}).status_code == 404
