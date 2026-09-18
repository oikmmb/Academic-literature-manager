"""AI 对话：会话持久化、DeepSeek/自定义兼容配置、多模态消息。"""
import json

import httpx
import pytest

from app.services.chat_ai import _chat_config, _user_content, chat


def _paper(client) -> int:
    r = client.post("/api/v1/papers", json={"title": "Chat Paper", "year": 2025, "doi": "10.9/chat"})
    return r.json()["data"]["id"]


class FakeResp:
    status_code = 200
    text = ""

    def __init__(self, content=None):
        self._c = content

    def json(self):
        if self._c is not None:
            return json.loads(self._c)
        return {"choices": [{"message": {"content": "这是回答。"}}]}


def test_chat_requires_key(client):
    pid = _paper(client)
    r = client.post(f"/api/v1/papers/{pid}/chat", json={"question": "这篇讲了什么"})
    assert r.status_code == 400
    assert "设置页" in r.json()["msg"]


def test_chat_and_history(client, monkeypatch):
    pid = _paper(client)
    client.put("/api/v1/settings/deepseek_api_key", json={"value": "sk-chat"})
    captured = {}

    def fake_post(url, **kwargs):
        captured["json"] = kwargs["json"]
        captured["url"] = url
        return FakeResp()

    monkeypatch.setattr(httpx, "post", fake_post)

    r = client.post(f"/api/v1/papers/{pid}/chat", json={"question": "这篇讲了什么"})
    assert r.status_code == 200, r.text
    assert r.json()["data"]["role"] == "assistant"
    # 系统 prompt 带文献标题
    assert "Chat Paper" in captured["json"]["messages"][0]["content"]
    assert captured["json"]["messages"][-1]["content"] == "这篇讲了什么"

    # 历史落库：user + assistant 两条
    items = client.get(f"/api/v1/papers/{pid}/chat/messages").json()["data"]["items"]
    assert len(items) == 2

    # 第二轮带历史
    r = client.post(f"/api/v1/papers/{pid}/chat", json={"question": "那方法部分呢"})
    assert len(captured["json"]["messages"]) == 4   # system + 2 历史 + 新问题

    # 清空
    client.delete(f"/api/v1/papers/{pid}/chat/messages")
    assert client.get(f"/api/v1/papers/{pid}/chat/messages").json()["data"]["items"] == []


def test_chat_with_image(client, monkeypatch):
    pid = _paper(client)
    client.put("/api/v1/settings/deepseek_api_key", json={"value": "sk-chat"})
    captured = {}

    def fake_post(url, **kwargs):
        captured["json"] = kwargs["json"]
        return FakeResp()

    monkeypatch.setattr(httpx, "post", fake_post)
    img_b64 = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUg=="
    r = client.post(f"/api/v1/papers/{pid}/chat", json={"question": "图里是什么", "image_base64": img_b64})
    assert r.status_code == 200
    content = captured["json"]["messages"][-1]["content"]
    assert isinstance(content, list)
    assert content[0]["type"] == "text"
    assert content[1]["type"] == "image_url"
    assert content[1]["image_url"]["url"] == img_b64


def test_openai_compat_config(client):
    client.put("/api/v1/settings/chat_provider", json={"value": "openai_compat"})
    client.put("/api/v1/settings/chat_base_url", json={"value": "https://api.example.com/v1"})
    client.put("/api/v1/settings/chat_api_key", json={"value": "sk-compat"})
    client.put("/api/v1/settings/chat_model", json={"value": "gpt-4o-mini"})

    db = client.app
    # 直接验证配置读取（通过 chat 调用路径）
    from app.db import SessionLocal
    db_s = SessionLocal()
    base, key, model = _chat_config(db_s)
    db_s.close()
    assert base == "https://api.example.com/v1"
    assert key == "sk-compat"
    assert model == "gpt-4o-mini"


def test_chat_missing_paper(client):
    client.put("/api/v1/settings/deepseek_api_key", json={"value": "sk"})
    r = client.post("/api/v1/papers/999/chat", json={"question": "hi"})
    assert r.status_code == 404
