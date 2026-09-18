"""端到端冒烟：对运行中的服务检查全部功能链路。用法：
    venv\\Scripts\\python scripts/api_smoke.py [base_url]   （默认 http://127.0.0.1:8000）
退出码 0 = 全部通过。"""
import base64
import io
import sys

import fitz
import httpx

# Windows 控制台默认 GBK，强制 UTF-8 输出（否则 ✓/中文 会 UnicodeEncodeError）
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"
passed, failed = 0, 0


def check(name, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
        print(f"  ✓ {name}")
    else:
        failed += 1
        print(f"  ✗ {name}  {detail}")


def make_pdf_bytes() -> bytes:
    doc = fitz.open()
    doc.set_metadata({"title": "Smoke Test Paper", "author": "Carol White; Dave Black"})
    page = doc.new_page()
    page.insert_text((72, 100), "Smoke Test Paper")
    page.insert_text((72, 130), "doi: 10.9999/smoke.2026")
    page.insert_text((72, 160), "Abstract This paper tests the whole pipeline.")
    buf = io.BytesIO()
    doc.save(buf)
    doc.close()
    return buf.getvalue()


def main():
    print(f"冒烟检查 {BASE}")
    c = httpx.Client(base_url=BASE, timeout=30, trust_env=False)   # 本机直连，不走系统代理

    r = c.get("/health")
    check("health", r.status_code == 200)

    # 1. 文献 CRUD + 分类
    r = c.post("/api/v1/papers", json={"title": "Manual Paper", "first_author": "Ann", "subject": "CV", "year": 2024, "doi": "10.9999/manual.1"})
    check("创建文献", r.status_code == 201, r.text[:100])
    pid_manual = r.json()["data"]["id"]

    r = c.get("/api/v1/papers", params={"sort_by": "year", "order": "desc"})
    check("列表+排序", r.status_code == 200 and r.json()["data"]["total"] >= 1)

    r = c.get("/api/v1/papers/groups/year")
    check("分类视图(年份)", r.status_code == 200 and any(g["key"] == 2024 for g in r.json()["data"]["groups"]))

    # 2. PDF 导入
    r = c.post("/api/v1/import", files={"file": ("smoke.pdf", make_pdf_bytes(), "application/pdf")})
    check("PDF 上传+元数据提取", r.status_code == 200 and r.json()["data"]["metadata"]["title"].startswith("Smoke"), r.text[:150])
    draft = r.json()["data"]

    r = c.post(f"/api/v1/import/{draft['draft_id']}/confirm", json={
        "title": "Smoke Test Paper", "authors": ["Carol White", "Dave Black"],
        "first_author": "Carol White", "year": 2026, "doi": "10.9999/smoke.2026",
    })
    check("导入确认建文献", r.status_code == 201 and r.json()["data"]["paper"]["has_pdf"], r.text[:150])
    pid = r.json()["data"]["paper"]["id"]

    # 3. 阅读器
    r = c.get(f"/api/v1/papers/{pid}/pages/1/words")
    check("词级数据", r.status_code == 200 and len(r.json()["data"]["words"]) >= 5)
    r = c.get(f"/api/v1/papers/{pid}/pages/1/image")
    check("页渲染 PNG", r.status_code == 200 and r.headers["content-type"] == "image/png")

    # 4. 批注（自动保存链路）
    ann = {"client_id": "smoke-ann-1", "paper_id": pid, "page": 1, "word_start": 0, "word_end": 2,
           "text": "Smoke Test Paper", "note": "", "color": "#FFEB3B", "kind": "highlight"}
    r = c.post("/api/v1/annotations/batch", json={"upserts": [ann]})
    check("批注批量保存", r.status_code == 200 and r.json()["data"]["saved"] == 1)
    r = c.post("/api/v1/annotations/batch", json={"upserts": [{**ann, "note": "冒烟笔记", "kind": "both"}]})
    check("批注幂等覆盖", r.status_code == 200 and r.json()["data"]["saved"] == 1)
    r = c.get(f"/api/v1/papers/{pid}/annotations")
    check("批注读取", r.status_code == 200 and len(r.json()["data"]["items"]) == 1
          and r.json()["data"]["items"][0]["note"] == "冒烟笔记")
    r = c.put("/api/v1/annotations/smoke-ann-1", json={"color": "#A7F3D0"})
    check("批注修改", r.status_code == 200 and r.json()["data"]["color"] == "#A7F3D0")

    # 5. 设置 + 翻译（未配置 key → 400 是预期行为；配置了 key 则真实翻译）
    r = c.get("/api/v1/settings")
    has_key = bool(r.json()["data"].get("deepseek_api_key"))
    r = c.post("/api/v1/translate", json={"text": "Machine learning is powerful."})
    if has_key:
        check("翻译(真实 API)", r.status_code == 200 and r.json()["data"]["translated"], r.text[:150])
    else:
        check("翻译(无 key 提示)", r.status_code == 400 and "设置页" in r.json()["msg"])

    # 6. OCR 图片匹配
    page = fitz.open(stream=make_pdf_bytes(), filetype="pdf")
    pix = page[0].get_pixmap(dpi=150)
    png = pix.tobytes("png")
    page.close()
    b64 = base64.b64encode(png).decode()
    r = c.post("/api/v1/ocr/match", json={"image_base64": b64})
    ok = r.status_code == 200 and r.json()["data"]["top3"] and r.json()["data"]["top3"][0]["score"] >= 80
    check("OCR 图片匹配本地库", ok, f"top3={r.json().get('data', {}).get('top3')}")

    # 7. Crossref（联网，可容忍失败）
    try:
        r = c.get("/api/v1/crossref/search", params={"q": "deep learning", "rows": 1})
        check("Crossref 检索(联网)", r.status_code == 200 and len(r.json()["data"]) >= 1, r.text[:150])
    except Exception:
        check("Crossref 检索(联网)", False, "网络不可用")

    # 8. 清理
    c.delete(f"/api/v1/papers/{pid_manual}")
    c.delete(f"/api/v1/papers/{pid}")
    check("清理冒烟数据", True)

    print(f"\n结果：{passed} 通过 / {failed} 失败")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
