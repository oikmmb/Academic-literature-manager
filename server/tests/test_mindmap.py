"""全局笔记（思维导图）：树 CRUD、子树删除、AI 生成（mock）、导入。"""
import io

import fitz
import httpx
import pytest

from app.services.mindmap_ai import _parse_tree, _clean_tree, extract_full_text


def _paper_with_pdf(client) -> int:
    doc = fitz.open()
    for i in range(2):
        page = doc.new_page()
        page.insert_text((72, 80), f"Deep learning page {i+1} introduction method result conclusion")
    buf = io.BytesIO()
    doc.save(buf)
    doc.close()
    r = client.post("/api/v1/import", files={"file": ("m.pdf", buf.getvalue(), "application/pdf")})
    draft = r.json()["data"]
    r = client.post(f"/api/v1/import/{draft['draft_id']}/confirm", json={"title": "Mindmap Paper"})
    return r.json()["data"]["paper"]["id"]


def test_tree_crud(client):
    pid = _paper_with_pdf(client)
    # 空树
    tree = client.get(f"/api/v1/papers/{pid}/mindmap").json()["data"]["tree"]
    assert tree["id"] is None and tree["children"] == []

    # 根 + 子 + 孙
    r = client.post(f"/api/v1/papers/{pid}/mindmap/nodes", json={"text": "核心主题"})
    root_id = r.json()["data"]["id"]
    r = client.post(f"/api/v1/papers/{pid}/mindmap/nodes", json={"parent_id": root_id, "text": "方法"})
    child_id = r.json()["data"]["id"]
    client.post(f"/api/v1/papers/{pid}/mindmap/nodes", json={"parent_id": child_id, "text": "实验细节"})

    tree = client.get(f"/api/v1/papers/{pid}/mindmap").json()["data"]["tree"]
    assert tree["text"] == "核心主题"
    assert tree["children"][0]["text"] == "方法"
    assert tree["children"][0]["children"][0]["text"] == "实验细节"

    # 编辑
    r = client.put(f"/api/v1/mindmap/nodes/{child_id}", json={"text": "研究方法"})
    assert r.json()["data"]["text"] == "研究方法"

    # 删除子树：删 child → 孙一并删
    r = client.delete(f"/api/v1/mindmap/nodes/{child_id}")
    assert r.json()["data"]["deleted"] == 2
    tree = client.get(f"/api/v1/papers/{pid}/mindmap").json()["data"]["tree"]
    assert tree["children"] == []


def test_generate_requires_key(client):
    pid = _paper_with_pdf(client)
    r = client.post(f"/api/v1/papers/{pid}/mindmap/generate")
    assert r.status_code == 400
    assert "设置页" in r.json()["msg"]


def test_generate_and_import(client, monkeypatch):
    pid = _paper_with_pdf(client)
    client.put("/api/v1/settings/deepseek_api_key", json={"value": "sk-test"})

    ai_json = '{"text":"根","children":[{"text":"分支A","children":[{"text":"要点1"}]},{"text":"分支B"}]}'

    class FakeResp:
        status_code = 200
        text = ""
        def json(self):
            return {"choices": [{"message": {"content": f"```json\n{ai_json}\n```"}}]}

    monkeypatch.setattr(httpx, "post", lambda *a, **k: FakeResp())

    r = client.post(f"/api/v1/papers/{pid}/mindmap/generate")
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["tree"]["children"][0]["text"] == "分支A"
    assert data["source_chars"] > 50

    # 导入（append 模式，无根 → 直接为根）
    r = client.post(f"/api/v1/papers/{pid}/mindmap/import", json={"tree": data["tree"], "mode": "append"})
    assert r.status_code == 201
    tree = r.json()["data"]["tree"]
    assert tree["children"][0]["children"][0]["text"] == "要点1"

    # replace 模式清空重建
    new_tree = {"text": "新根", "children": []}
    r = client.post(f"/api/v1/papers/{pid}/mindmap/import", json={"tree": new_tree, "mode": "replace"})
    tree = r.json()["data"]["tree"]
    assert tree["text"] == "新根" and tree["children"] == []


def test_parse_tree_robust():
    t = _parse_tree('```json\n{"text":"a","children":[]}\n```')
    assert t["text"] == "a"
    t = _parse_tree('前言 {"text":"b"} 后缀')
    assert t["text"] == "b"


def test_clean_tree_limits():
    big = {"text": "x" * 200, "children": [{"text": f"c{i}"} for i in range(20)]}
    t = _clean_tree(big)
    assert len(t["text"]) <= 100
    assert len(t["children"]) <= 8


def test_extract_full_text_truncates():
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 80), "word " * 100)
    buf = io.BytesIO()
    doc.save(buf)
    doc.close()
    import tempfile
    from pathlib import Path
    p = Path(tempfile.mkdtemp()) / "t.pdf"
    p.write_bytes(buf.getvalue())
    text = extract_full_text(str(p))
    assert len(text) > 0


def test_node_position_save(client):
    """节点拖拽位置持久化（x/y 布局坐标）。"""
    pid = _paper_with_pdf(client)
    r = client.post(f"/api/v1/papers/{pid}/mindmap/nodes", json={"text": "根"})
    nid = r.json()["data"]["id"]
    r = client.put(f"/api/v1/mindmap/nodes/{nid}", json={"x": 3.5, "y": 1.25})
    assert r.status_code == 200
    out = r.json()["data"]
    assert out["x"] == 3.5 and out["y"] == 1.25
    # 树读取含 x/y
    tree = client.get(f"/api/v1/papers/{pid}/mindmap").json()["data"]["tree"]
    assert tree["x"] == 3.5 and tree["y"] == 1.25
    # 只改文本不动位置
    client.put(f"/api/v1/mindmap/nodes/{nid}", json={"text": "改"})
    tree = client.get(f"/api/v1/papers/{pid}/mindmap").json()["data"]["tree"]
    assert tree["x"] == 3.5 and tree["text"] == "改"
