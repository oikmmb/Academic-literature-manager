"""批注：批量幂等保存、单条修改/删除、按文献读取。"""


def _paper(client):
    r = client.post("/api/v1/papers", json={"title": "Paper X", "year": 2020, "doi": "10.1/x"})
    return r.json()["data"]["id"]


def _ann(paper_id, **kw):
    base = {
        "client_id": "11111111-2222-3333-4444-555555555555",
        "paper_id": paper_id,
        "page": 2,
        "word_start": 10, "word_end": 23,
        "char_start": 0, "char_end": 2,
        "text": "selected text", "note": "", "color": "#FFEB3B", "kind": "highlight",
    }
    base.update(kw)
    return base


def test_batch_upsert_idempotent(client):
    pid = _paper(client)
    r = client.post("/api/v1/annotations/batch", json={"upserts": [_ann(pid)]})
    assert r.json()["data"]["saved"] == 1
    # 同 client_id 再提交 = 覆盖更新（注释内容变化）
    r = client.post("/api/v1/annotations/batch",
                    json={"upserts": [_ann(pid, note="新笔记", kind="both")]})
    assert r.json()["data"]["saved"] == 1
    items = client.get(f"/api/v1/papers/{pid}/annotations").json()["data"]["items"]
    assert len(items) == 1
    assert items[0]["note"] == "新笔记" and items[0]["kind"] == "both"


def test_batch_delete(client):
    pid = _paper(client)
    ann_id = _ann(pid)["client_id"]
    client.post("/api/v1/annotations/batch", json={"upserts": [_ann(pid)]})
    r = client.post("/api/v1/annotations/batch", json={"deletes": [ann_id]})
    assert r.json()["data"]["deleted"] == 1
    assert client.get(f"/api/v1/papers/{pid}/annotations").json()["data"]["items"] == []


def test_list_by_page(client):
    pid = _paper(client)
    client.post("/api/v1/annotations/batch", json={"upserts": [
        _ann(pid, client_id="a-1", page=1),
        _ann(pid, client_id="a-2", page=2),
    ]})
    assert len(client.get(f"/api/v1/papers/{pid}/annotations", params={"page": 1}).json()["data"]["items"]) == 1


def test_patch_and_delete_single(client):
    pid = _paper(client)
    aid = _ann(pid)["client_id"]
    client.post("/api/v1/annotations/batch", json={"upserts": [_ann(pid)]})
    r = client.put(f"/api/v1/annotations/{aid}", json={"color": "#FF0000"})
    assert r.json()["data"]["color"] == "#FF0000"
    assert client.delete(f"/api/v1/annotations/{aid}").status_code == 200
    assert client.delete(f"/api/v1/annotations/{aid}").status_code == 404


def test_annotation_opacity(client):
    """高亮透明度：batch 保存、patch 修改、范围校验。"""
    pid = _paper(client)
    aid = _ann(pid)["client_id"]
    client.post("/api/v1/annotations/batch", json={"upserts": [_ann(pid, opacity=0.3)]})
    items = client.get(f"/api/v1/papers/{pid}/annotations").json()["data"]["items"]
    assert items[0]["opacity"] == 0.3
    # 默认值
    client.post("/api/v1/annotations/batch", json={"upserts": [_ann(pid, client_id="b-1")]})
    items = {a["id"]: a for a in client.get(f"/api/v1/papers/{pid}/annotations").json()["data"]["items"]}
    assert items["b-1"]["opacity"] == 0.55
    # patch 修改
    r = client.put(f"/api/v1/annotations/{aid}", json={"opacity": 0.9})
    assert r.json()["data"]["opacity"] == 0.9
    # 越界 422
    assert client.put(f"/api/v1/annotations/{aid}", json={"opacity": 1.5}).status_code == 422


def test_annotations_of_missing_paper(client):
    assert client.get("/api/v1/papers/999/annotations").status_code == 404
