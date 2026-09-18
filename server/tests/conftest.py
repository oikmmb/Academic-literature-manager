"""测试夹具：在导入 app 之前把数据库与数据目录指向临时位置，避免污染真实数据。"""
import os
import tempfile
from pathlib import Path

_tmp_dir = Path(tempfile.mkdtemp(prefix="lit_test_"))
os.environ["LIT_DATA_DIR"] = str(_tmp_dir)
os.environ["LIT_DB_URL"] = f"sqlite:///{(_tmp_dir / 'test.db').as_posix()}"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.db import Base, engine  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(autouse=True)
def clean_tables():
    """每个测试前后清空全部表 + CLIP/形状索引文件（避免测试顺序耦合）。"""
    for table in reversed(Base.metadata.sorted_tables):
        with engine.begin() as conn:
            conn.execute(table.delete())
    from app.config import CACHE_DIR, DATA_DIR
    for f in ("clip_feats.npy", "clip_meta.json", "page_texts.json", "shape_index.json"):
        p = DATA_DIR / f
        p.unlink(missing_ok=True)
    for p in CACHE_DIR.glob("*.png"):   # 渲染缓存也清，避免 pid 复用串档
        p.unlink(missing_ok=True)
    yield
    for table in reversed(Base.metadata.sorted_tables):
        with engine.begin() as conn:
            conn.execute(table.delete())


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c
