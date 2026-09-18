"""全局配置：路径、阈值、DeepSeek 默认值。"""
import os
import sys
from pathlib import Path

def _default_data_dir() -> Path:
    """安装版默认数据目录：F:\论文\data（避免 C 盘膨胀）；F 盘不存在时回退用户目录。"""
    env = os.environ.get("LIT_DATA_DIR")
    if env:
        return Path(env)
    if Path("F:/").exists():
        return Path("F:/论文/data")
    return Path.home() / ".lit-manager" / "data"


if getattr(sys, "frozen", False):
    # PyInstaller 打包后：资源在 _MEIPASS，用户数据外置（升级不丢数据）
    BASE_DIR = Path(sys._MEIPASS)
    SERVER_DIR = BASE_DIR / "server"
    DATA_DIR = _default_data_dir()
else:
    BASE_DIR = Path(__file__).resolve().parents[2]   # lit-manager 项目根
    SERVER_DIR = BASE_DIR / "server"
    # 测试时用 LIT_DATA_DIR / LIT_DB_URL 指向临时目录（conftest.py 设置）
    DATA_DIR = Path(os.environ.get("LIT_DATA_DIR", BASE_DIR / "data"))

PDF_DIR = DATA_DIR / "pdfs"
CACHE_DIR = DATA_DIR / "cache"
MODELS_DIR = BASE_DIR / "models"
WEB_DIR = BASE_DIR / "web"

DB_URL = os.environ.get("LIT_DB_URL", f"sqlite:///{(DATA_DIR / 'lit.db').as_posix()}")

# 图片匹配：Top3 全低于该分视为未命中，触发 Crossref 联网补录
MATCH_THRESHOLD = 55

# 阅读器页渲染分辨率（固定，前端只做 CSS 缩放）
RENDER_DPI = 150

# DeepSeek 翻译默认值（可在设置页覆盖）
DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEEPSEEK_MODEL = "deepseek-chat"
