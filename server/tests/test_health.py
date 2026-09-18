"""M1 冒烟：health + 退出端点 + envelope。"""
from app.main import quit_event


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["code"] == 0


def test_health_404_envelope(client):
    r = client.get("/api/v1/papers/99999")
    assert r.status_code == 404
    body = r.json()
    assert body["code"] == 404 and "msg" in body


def test_quit_endpoint(client):
    quit_event.clear()
    r = client.post("/api/v1/app/quit")
    assert r.status_code == 200
    assert quit_event.is_set()


def test_422_envelope(client):
    """参数校验失败也走统一 envelope（前端据此展示具体错误）。"""
    r = client.post("/api/v1/annotations/batch", json={"upserts": [{"id": "no-client-id"}]})
    assert r.status_code == 422
    body = r.json()
    assert body["code"] == 422 and "client_id" in body["msg"]
