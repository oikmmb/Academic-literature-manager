"""OCR 路由：无效输入防护（有效图片的引擎集成测试在 M7 冒烟中做，依赖模型下载）。"""
import base64


def test_invalid_base64(client):
    r = client.post("/api/v1/ocr/match", json={"image_base64": "not-base64!!"})
    assert r.status_code == 400


def test_empty_image(client):
    r = client.post("/api/v1/ocr/match", json={"image_base64": ""})
    assert r.status_code == 400


def test_oversize_image(client):
    big = base64.b64encode(b"x" * (10 * 1024 * 1024 + 1)).decode()
    r = client.post("/api/v1/ocr/match", json={"image_base64": big})
    assert r.status_code == 400
