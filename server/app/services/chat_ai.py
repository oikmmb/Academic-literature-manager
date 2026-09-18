"""AI 对话：OpenAI 兼容 chat/completions（DeepSeek 或自定义兼容服务），支持图像输入。

提供商配置（settings）：
  chat_provider = deepseek（复用翻译的 DeepSeek 凭据） | openai_compat（chat_base_url/chat_api_key/chat_model）
多模态：图片消息按 OpenAI 视觉协议 content 数组发送（需视觉模型，如 gpt-4o / qwen-vl）。
"""
import json

import httpx

from ..config import DEEPSEEK_BASE_URL, DEEPSEEK_MODEL
from ..models import Setting

SYSTEM_PROMPT = (
    "你是学术文献阅读助手，回答准确、简洁、专业。"
    "当用户引用论文片段提问时，请基于引用内容作答；涉及论文全文的问题，先说明依据。"
    "中文回答，术语保留英文原名。"
)

MAX_HISTORY = 20          # 最多携带的历史消息轮数
MAX_CONTEXT_CHARS = 8000  # 引用文本截断


def _get_setting(db, key: str, default: str) -> str:
    row = db.get(Setting, key)
    return row.value if row and row.value else default


def _chat_config(db) -> tuple[str, str, str]:
    """返回 (base_url, api_key, model)。"""
    provider = _get_setting(db, "chat_provider", "deepseek")
    if provider == "openai_compat":
        base = _get_setting(db, "chat_base_url", "").rstrip("/")
        key = _get_setting(db, "chat_api_key", "")
        model = _get_setting(db, "chat_model", "")
        if not base or not key or not model:
            raise ValueError("请先在设置页配置对话 API（地址 / Key / 模型）")
        return base, key, model
    key = _get_setting(db, "deepseek_api_key", "")
    if not key:
        raise ValueError("请先在设置页配置 DeepSeek API Key")
    return _get_setting(db, "deepseek_base_url", DEEPSEEK_BASE_URL).rstrip("/"), key, _get_setting(db, "deepseek_model", DEEPSEEK_MODEL)


def _user_content(text: str, image_b64: str | None) -> object:
    """OpenAI 消息 content：纯文本或 [text, image_url]。"""
    if not image_b64:
        return text[:MAX_CONTEXT_CHARS]
    return [
        {"type": "text", "text": text[:MAX_CONTEXT_CHARS]},
        {"type": "image_url", "image_url": {"url": image_b64[:4_000_000]}},
    ]


def chat(paper_title: str, history: list[dict], question: str, image_b64: str | None, db) -> str:
    """历史消息为 {role, content(dict)} 列表；返回助手回复文本。"""
    base_url, api_key, model = _chat_config(db)
    messages = [{"role": "system", "content": SYSTEM_PROMPT + f"\n当前文献：《{paper_title}》"}]
    for m in history[-MAX_HISTORY:]:
        try:
            content = json.loads(m["content"])
        except Exception:
            content = {"text": str(m["content"])}
        text = content.get("text") or ""
        image = content.get("image")
        if m["role"] in ("user", "assistant") and (text or image):
            messages.append({"role": m["role"], "content": _user_content(text, image)})
    messages.append({"role": "user", "content": _user_content(question, image_b64)})

    resp = httpx.post(
        f"{base_url}/chat/completions",
        headers={"Authorization": f"Bearer {api_key}"},
        json={"model": model, "messages": messages, "temperature": 0.3, "stream": False},
        timeout=180,
    )
    if resp.status_code == 401:
        raise ValueError("对话 API Key 无效（401），请检查设置")
    if resp.status_code == 402:
        raise ValueError("对话 API 账户余额不足（402）")
    if resp.status_code != 200:
        raise ValueError(f"对话 API 错误 ({resp.status_code})：{resp.text[:200]}")
    return resp.json()["choices"][0]["message"]["content"].strip()
