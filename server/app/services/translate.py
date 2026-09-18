"""翻译服务：DeepSeek / 有道智云 / 百度翻译 三提供商可切换。
缓存键 = sha256(提供商身份 + 规范化文本)，防换提供商/换凭据/换模型串缓存。"""
import hashlib
import re
import time
import uuid

import httpx

from ..config import DEEPSEEK_BASE_URL, DEEPSEEK_MODEL
from ..models import Setting, TranslationCache

SYSTEM_PROMPT = (
    "你是学术论文英译中专家。请将用户提供的英文文本翻译成流畅、准确的中文，"
    "保留专业术语的准确性。只输出译文本身，不要任何解释或格式标记。若输入已是中文则原样返回。"
)

PROVIDERS = ("deepseek", "youdao", "baidu")
# 每个提供商的 settings 键
PROVIDER_KEYS = {
    "deepseek": ("deepseek_api_key", "deepseek_base_url", "deepseek_model"),
    "youdao": ("youdao_app_key", "youdao_app_secret"),
    "baidu": ("baidu_ak", "baidu_sk"),
}
# 长度上限（超过截断，学术选段一般远小于此；翻译结果附注截断提示）
MAX_TEXT = 4800


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _get_setting(db, key: str, default: str) -> str:
    row = db.get(Setting, key)
    return row.value if row and row.value else default


def _identity(db, provider: str) -> str:
    """缓存键中的提供商身份：换凭据/模型即隔离缓存。"""
    if provider == "deepseek":
        base = _get_setting(db, "deepseek_base_url", DEEPSEEK_BASE_URL).rstrip("/")
        model = _get_setting(db, "deepseek_model", DEEPSEEK_MODEL)
        key = _get_setting(db, "deepseek_api_key", "")
        return f"deepseek|{base}|{model}|{key[:16]}"
    if provider == "youdao":
        return f"youdao|{_get_setting(db, 'youdao_app_key', '')[:16]}"
    return f"baidu|{_get_setting(db, 'baidu_ak', '')[:16]}"


def _cache_key(identity: str, text: str) -> str:
    return hashlib.sha256(f"{identity}|{_normalize(text)}".encode()).hexdigest()


def _from_cache(db, key: str) -> str | None:
    hit = db.get(TranslationCache, key)
    if hit:
        hit.hit_count += 1
        db.commit()
        return hit.target_text
    return None


def _to_cache(db, key: str, identity: str, text: str, translated: str) -> None:
    db.add(TranslationCache(text_hash=key, source_text=text, target_text=translated, model=identity[:200]))
    db.commit()


# ---------------- DeepSeek ----------------

def _translate_deepseek(db, text: str) -> str:
    api_key = _get_setting(db, "deepseek_api_key", "")
    if not api_key:
        raise ValueError("请先在设置页配置 DeepSeek API Key")
    base_url = _get_setting(db, "deepseek_base_url", DEEPSEEK_BASE_URL).rstrip("/")
    model = _get_setting(db, "deepseek_model", DEEPSEEK_MODEL)
    resp = httpx.post(
        f"{base_url}/chat/completions",
        headers={"Authorization": f"Bearer {api_key}"},
        json={
            "model": model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": text},
            ],
            "temperature": 0.3,
            "stream": False,
        },
        timeout=15,
    )
    if resp.status_code == 401:
        raise ValueError("DeepSeek API Key 无效（401），请检查设置")
    if resp.status_code == 402:
        raise ValueError("DeepSeek 账户余额不足（402）")
    if resp.status_code != 200:
        raise ValueError(f"DeepSeek API 错误 ({resp.status_code})：{resp.text[:200]}")
    return resp.json()["choices"][0]["message"]["content"].strip()


# ---------------- 有道智云 ----------------

YOUDAO_API = "https://openapi.youdao.com/api"
YOUDAO_ERRORS = {
    "101": "App Key 无效，请检查有道智云设置",
    "102": "应用被禁用或额度用尽",
    "108": "App Key 无效（108）",
    "109": "应用渠道号无效",
    "111": "无额度（免费额度已用完）",
    "201": "解密失败（Secret 错误）",
    "202": "签名错误（Secret 与 Key 不匹配）",
    "401": "账户欠费",
    "411": "请求文本过长",
}


def _translate_youdao(db, text: str) -> str:
    app_key = _get_setting(db, "youdao_app_key", "")
    app_secret = _get_setting(db, "youdao_app_secret", "")
    if not app_key or not app_secret:
        raise ValueError("请先在设置页配置有道智云的 App Key 与密钥（ai.youdao.com 免费申请）")
    salt = uuid.uuid4().hex
    sign = hashlib.sha256(f"{app_key}{text}{salt}{app_secret}".encode()).hexdigest()
    resp = httpx.post(YOUDAO_API, data={
        "q": text, "from": "en", "to": "zh-CHS",
        "appKey": app_key, "salt": salt, "sign": sign,
    }, timeout=15)
    try:
        data = resp.json()
    except Exception:
        raise ValueError(f"有道翻译响应异常 ({resp.status_code})")
    code = str(data.get("errorCode", ""))
    if code != "0":
        raise ValueError(YOUDAO_ERRORS.get(code, f"有道翻译错误 {code}：{data.get('msg', '')}"))
    return data["translation"][0]


# ---------------- 百度翻译 ----------------

BAIDU_TOKEN_API = "https://aip.baidubce.com/oauth/2.0/token"
BAIDU_TRANS_API = "https://aip.baidubce.com/rpc/2.0/mt/texttrans/v1"
_baidu_token_cache = {"token": "", "expires": 0.0}

BAIDU_ERRORS = {
    "52001": "请求超时，请重试",
    "52002": "系统错误，请重试",
    "52003": "未授权（AK/SK 无效）",
    "54000": "必填参数为空",
    "54001": "签名/认证错误",
    "54003": "访问频率受限",
    "54004": "账户余额不足",
    "54005": "长query请求频繁",
    "58001": "语言方向不支持",
    "58003": "IP 受限（请到百度平台绑定 IP）",
}


def _baidu_token(ak: str, sk: str) -> str:
    """百度 access_token（约 30 天有效），进程内缓存。"""
    now = time.time()
    if _baidu_token_cache["token"] and _baidu_token_cache["expires"] > now + 60:
        return _baidu_token_cache["token"]
    resp = httpx.post(BAIDU_TOKEN_API, params={
        "grant_type": "client_credentials", "client_id": ak, "client_secret": sk,
    }, timeout=15)
    data = resp.json()
    if "access_token" not in data:
        raise ValueError(f"百度翻译认证失败：{data.get('error_description') or data}")
    _baidu_token_cache["token"] = data["access_token"]
    _baidu_token_cache["expires"] = now + data.get("expires_in", 2592000)
    return _baidu_token_cache["token"]


def _translate_baidu(db, text: str) -> str:
    ak = _get_setting(db, "baidu_ak", "")
    sk = _get_setting(db, "baidu_sk", "")
    if not ak or not sk:
        raise ValueError("请先在设置页配置百度翻译的 API Key 与 Secret Key（fanyi-api.baidu.com 免费申请）")
    token = _baidu_token(ak, sk)
    resp = httpx.post(f"{BAIDU_TRANS_API}?access_token={token}", json={
        "q": text, "from": "en", "to": "zh",
    }, timeout=15)
    try:
        data = resp.json()
    except Exception:
        raise ValueError(f"百度翻译响应异常 ({resp.status_code})")
    if "result" not in data:
        code = str(data.get("error_code", ""))
        raise ValueError(BAIDU_ERRORS.get(code, f"百度翻译错误 {code}：{data.get('error_msg', data)}"))
    return "\n".join(item["dst"] for item in data["result"]["trans_result"])


# ---------------- 统一入口 ----------------

def translate(text: str, db) -> dict:
    """返回 {"translated": str, "cached": bool}。未配置凭据抛 ValueError（中文提示）。"""
    text = _normalize(text)
    if not text:
        raise ValueError("翻译文本为空")
    truncated = ""
    if len(text) > MAX_TEXT:
        truncated = "（原文过长已截断）"
        text = text[:MAX_TEXT]

    provider = _get_setting(db, "translate_provider", "deepseek")
    if provider not in PROVIDERS:
        provider = "deepseek"
    identity = _identity(db, provider)
    key = _cache_key(identity, text)

    cached = _from_cache(db, key)
    if cached is not None:
        return {"translated": cached, "cached": True}

    try:
        if provider == "youdao":
            translated = _translate_youdao(db, text)
        elif provider == "baidu":
            translated = _translate_baidu(db, text)
        else:
            translated = _translate_deepseek(db, text)
    except httpx.HTTPError:
        raise ValueError("翻译服务网络请求失败，请检查网络或代理设置")

    _to_cache(db, key, identity, text, translated)
    return {"translated": translated + truncated, "cached": False}
