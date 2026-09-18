"""翻译：DeepSeek 调用（mock）、缓存命中、设置读写。"""
import httpx
import pytest

from app.models import Setting, TranslationCache
from app.services import translate as ts


@pytest.fixture
def api_key(client):
    client.put("/api/v1/settings/deepseek_api_key", json={"value": "sk-test"})
    yield
    client.put("/api/v1/settings/deepseek_api_key", json={"value": ""})


class FakeResp:
    def __init__(self, status_code=200, content=None):
        self.status_code = status_code
        self._content = content

    @property
    def text(self):
        return str(self._content)

    def json(self):
        import json as _json
        if self._content is not None:
            return _json.loads(self._content)
        return {"choices": [{"message": {"content": "深度学习是人工智能的一个子集。"}}]}


def test_translate_requires_key(client):
    r = client.post("/api/v1/translate", json={"text": "hello"})
    assert r.status_code == 400


def test_translate_and_cache(client, api_key, monkeypatch):
    calls = []

    def fake_post(url, **kwargs):
        calls.append(url)
        assert kwargs["headers"]["Authorization"] == "Bearer sk-test"
        assert kwargs["json"]["model"] == "deepseek-chat"
        return FakeResp()

    monkeypatch.setattr(httpx, "post", fake_post)

    r = client.post("/api/v1/translate", json={"text": "  Machine   learning "})
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["translated"] == "深度学习是人工智能的一个子集。"
    assert data["cached"] is False

    # 同文本（规范化后相同）二次调用命中缓存，不再调 API
    r = client.post("/api/v1/translate", json={"text": "Machine learning"})
    assert r.json()["data"]["cached"] is True
    assert len(calls) == 1


def test_translate_401(client, api_key, monkeypatch):
    def fake_post(url, **kwargs):
        return FakeResp(401, "invalid key")
    monkeypatch.setattr(httpx, "post", fake_post)
    r = client.post("/api/v1/translate", json={"text": "hello"})
    assert r.status_code == 400
    assert "401" in r.json()["msg"]


def test_settings_crud(client):
    assert client.get("/api/v1/settings").json()["data"] == {}
    client.put("/api/v1/settings/deepseek_api_key", json={"value": "sk-abc"})
    assert client.get("/api/v1/settings").json()["data"]["deepseek_api_key"] == "sk-abc"
    client.put("/api/v1/settings/deepseek_api_key", json={"value": "sk-new"})
    assert client.get("/api/v1/settings").json()["data"]["deepseek_api_key"] == "sk-new"


def test_cache_key_includes_model(client, api_key):
    """换模型后同文本不串缓存。"""
    t1 = ts._cache_key("deepseek|https://api.deepseek.com|deepseek-chat|sk1", "hello")
    t2 = ts._cache_key("deepseek|https://api.deepseek.com|deepseek-reasoner|sk1", "hello")
    t3 = ts._cache_key("deepseek|https://other.com|deepseek-chat|sk1", "hello")
    assert len({t1, t2, t3}) == 3


# ---------------- 有道 ----------------

def test_youdao_translate(client, monkeypatch):
    client.put("/api/v1/settings/translate_provider", json={"value": "youdao"})
    client.put("/api/v1/settings/youdao_app_key", json={"value": "yd-key"})
    client.put("/api/v1/settings/youdao_app_secret", json={"value": "yd-secret"})

    captured = {}

    def fake_post(url, **kwargs):
        captured["url"] = url
        captured["data"] = kwargs["data"]
        # 校验签名 = sha256(appKey + q + salt + secret)
        import hashlib
        d = kwargs["data"]
        expect = hashlib.sha256(f"{d['appKey']}{d['q']}{d['salt']}yd-secret".encode()).hexdigest()
        assert d["sign"] == expect
        return FakeResp(200, '{"errorCode":"0","translation":["注意力机制。"]}')

    monkeypatch.setattr(httpx, "post", fake_post)

    r = client.post("/api/v1/translate", json={"text": "attention mechanism"})
    assert r.status_code == 200, r.text
    assert r.json()["data"]["translated"] == "注意力机制。"
    assert captured["url"].startswith("https://openapi.youdao.com")
    assert captured["data"]["from"] == "en" and captured["data"]["to"] == "zh-CHS"


def test_youdao_error(client, monkeypatch):
    client.put("/api/v1/settings/translate_provider", json={"value": "youdao"})
    client.put("/api/v1/settings/youdao_app_key", json={"value": "k"})
    client.put("/api/v1/settings/youdao_app_secret", json={"value": "s"})
    monkeypatch.setattr(httpx, "post", lambda *a, **k: FakeResp(200, '{"errorCode":"111","msg":"no quota"}'))
    r = client.post("/api/v1/translate", json={"text": "hello"})
    assert r.status_code == 400
    assert "额度" in r.json()["msg"]


def test_youdao_requires_credentials(client):
    client.put("/api/v1/settings/translate_provider", json={"value": "youdao"})
    r = client.post("/api/v1/translate", json={"text": "hello"})
    assert r.status_code == 400
    assert "有道" in r.json()["msg"]


# ---------------- 百度 ----------------

def test_baidu_translate_with_token(client, monkeypatch):
    ts._baidu_token_cache["token"] = ""
    ts._baidu_token_cache["expires"] = 0
    client.put("/api/v1/settings/translate_provider", json={"value": "baidu"})
    client.put("/api/v1/settings/baidu_ak", json={"value": "ak1"})
    client.put("/api/v1/settings/baidu_sk", json={"value": "sk1"})

    calls = []

    def fake_post(url, **kwargs):
        calls.append(url)
        if "oauth" in url:   # token 接口
            return FakeResp(200, '{"access_token":"tok123","expires_in":2592000}')
        assert kwargs["json"]["to"] == "zh"
        return FakeResp(200, '{"result":{"trans_result":[{"src":"deep","dst":"深度"}]}}')

    monkeypatch.setattr(httpx, "post", fake_post)

    r = client.post("/api/v1/translate", json={"text": "deep"})
    assert r.status_code == 200, r.text
    assert r.json()["data"]["translated"] == "深度"
    # 第一次调 token 接口，第二次调翻译接口
    assert any("token" in u for u in calls)
    assert any("texttrans" in u for u in calls)


def test_baidu_auth_error(client, monkeypatch):
    ts._baidu_token_cache["token"] = ""
    ts._baidu_token_cache["expires"] = 0
    client.put("/api/v1/settings/translate_provider", json={"value": "baidu"})
    client.put("/api/v1/settings/baidu_ak", json={"value": "ak"})
    client.put("/api/v1/settings/baidu_sk", json={"value": "sk"})
    monkeypatch.setattr(httpx, "post", lambda *a, **k: FakeResp(200, '{"error":"invalid_client","error_description":"bad"}'))
    r = client.post("/api/v1/translate", json={"text": "hello"})
    assert r.status_code == 400
    assert "认证失败" in r.json()["msg"]


def test_provider_switch_isolates_cache(client, api_key, monkeypatch):
    """换提供商后同文本不命中旧缓存（身份串隔离）。"""
    monkeypatch.setattr(httpx, "post", lambda *a, **k: FakeResp())
    r1 = client.post("/api/v1/translate", json={"text": "hello"})   # deepseek
    assert r1.json()["data"]["cached"] is False

    client.put("/api/v1/settings/translate_provider", json={"value": "youdao"})
    client.put("/api/v1/settings/youdao_app_key", json={"value": "k"})
    client.put("/api/v1/settings/youdao_app_secret", json={"value": "s"})
    monkeypatch.setattr(httpx, "post", lambda *a, **k: FakeResp(200, '{"errorCode":"0","translation":["好"]}'))
    r2 = client.post("/api/v1/translate", json={"text": "hello"})   # youdao
    assert r2.json()["data"]["cached"] is False
    assert r2.json()["data"]["translated"] == "好"
