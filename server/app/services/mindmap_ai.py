"""AI 思维导图生成：提取全文文本 → DeepSeek 结构化要点树（JSON）。

复用设置页的 DeepSeek 凭据（翻译同一 key）。全文截断至 MAX_CHARS 控制成本。
"""
import json
import re

import fitz
import httpx

from ..config import DEEPSEEK_BASE_URL, DEEPSEEK_MODEL
from ..models import Setting

MAX_CHARS = 30000
SYSTEM_PROMPT = (
    "你是学术论文阅读助手。用户给你一篇论文的文本，请梳理其核心思路与要点，"
    "输出一个层级结构（思维导图树），用于帮助读者快速把握全文脉络。\n"
    "要求：\n"
    "1. 根节点为论文核心主题（一句话）\n"
    "2. 第二层为主题分支（研究背景/问题、方法、关键结果、结论等，按论文实际结构）\n"
    "3. 第三层及以下为具体要点，每条控制在 25 字以内\n"
    "4. 总节点数 20~40 个，最多 4 层\n"
    "5. 只输出 JSON，格式：{\"text\":\"根\",\"children\":[{\"text\":\"分支\",\"children\":[...]}]}，"
    "不要输出任何解释或代码块标记"
)


def _get_setting(db, key: str, default: str) -> str:
    row = db.get(Setting, key)
    return row.value if row and row.value else default


def extract_full_text(pdf_path: str) -> str:
    """全文提取（用于 AI 梳理），截断控制成本。"""
    doc = fitz.open(pdf_path)
    try:
        parts = [doc[i].get_text() for i in range(doc.page_count)]
    finally:
        doc.close()
    text = "\n\n".join(parts)
    text = re.sub(r"[ \t]+", " ", text)
    if len(text) > MAX_CHARS:
        # 保留开头（摘要/引言）+ 各页均匀采样
        head = text[: MAX_CHARS // 2]
        rest = text[MAX_CHARS // 2:]
        step = max(1, len(rest) // (MAX_CHARS // 4))
        body = rest[::step][: MAX_CHARS // 4]
        tail = text[-MAX_CHARS // 4:]
        text = head + body + tail
    return text


def _parse_tree(raw: str) -> dict:
    """容错解析模型输出：剥代码块/前后缀，取第一个 JSON 对象。"""
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.S)
    if m:
        raw = m.group(1)
    else:
        start = raw.find("{")
        if start >= 0:
            raw = raw[start:]
            # 找配对的最后一个 }
            depth = 0
            end = -1
            for i, ch in enumerate(raw):
                if ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        end = i + 1
                        break
            raw = raw[:end]
    return json.loads(raw)


def _clean_tree(node: dict) -> dict:
    """清理/限宽：确保 text 字段存在，子树递归，最多 4 层、每层最多 8 子。"""
    text = str(node.get("text", "")).strip()[:100]
    if not text:
        text = "要点"
    children = node.get("children") or []
    if isinstance(children, list) and children:
        return {"text": text, "children": [_clean_tree(c) for c in children[:8]]}
    return {"text": text, "children": []}


def generate_mindmap(paper_id: int, pdf_path: str, db) -> dict:
    """调 DeepSeek 生成要点树。返回 {'tree': {...}, 'source_chars': int}。"""
    api_key = _get_setting(db, "deepseek_api_key", "")
    if not api_key:
        raise ValueError("请先在设置页配置 DeepSeek API Key（翻译与 AI 笔记共用）")
    base_url = _get_setting(db, "deepseek_base_url", DEEPSEEK_BASE_URL).rstrip("/")
    model = _get_setting(db, "deepseek_model", DEEPSEEK_MODEL)

    text = extract_full_text(pdf_path)
    if not text.strip():
        raise ValueError("该文献无可提取的文本（可能是扫描版）")

    resp = httpx.post(
        f"{base_url}/chat/completions",
        headers={"Authorization": f"Bearer {api_key}"},
        json={
            "model": model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": text[:MAX_CHARS]},
            ],
            "temperature": 0.3,
            "stream": False,
        },
        timeout=120,
    )
    if resp.status_code == 401:
        raise ValueError("DeepSeek API Key 无效（401），请检查设置")
    if resp.status_code == 402:
        raise ValueError("DeepSeek 账户余额不足（402）")
    if resp.status_code != 200:
        raise ValueError(f"DeepSeek API 错误 ({resp.status_code})：{resp.text[:200]}")

    raw = resp.json()["choices"][0]["message"]["content"]
    try:
        tree = _clean_tree(_parse_tree(raw))
    except Exception:
        raise ValueError("AI 返回的内容无法解析为结构树，请重试")
    return {"tree": tree, "source_chars": len(text)}
