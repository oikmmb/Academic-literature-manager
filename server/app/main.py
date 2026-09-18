"""FastAPI 装配：CORS、路由、/health、退出端点、静态挂载（必须放所有路由之后）。"""
import threading

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from . import config, models  # noqa: F401  确保模型注册到 Base.metadata
from .db import Base, SessionLocal, engine
from .routers import annotations, chat, crossref, imports, mindmap, ocr, papers, reader, refs, supplements, translate

Base.metadata.create_all(engine)


def _ensure_annotation_columns() -> None:
    """存量库迁移：annotations 表补充 supp_id / opacity 列（create_all 不会给已有表加列）。"""
    from sqlalchemy import text
    with engine.connect() as conn:
        cols = [row[1] for row in conn.execute(text("PRAGMA table_info(annotations)"))]
        if "supp_id" not in cols:
            conn.execute(text("ALTER TABLE annotations ADD COLUMN supp_id INTEGER NOT NULL DEFAULT 0"))
        if "opacity" not in cols:
            conn.execute(text("ALTER TABLE annotations ADD COLUMN opacity FLOAT NOT NULL DEFAULT 0.55"))
        if "segments" not in cols:
            conn.execute(text("ALTER TABLE annotations ADD COLUMN segments TEXT"))
        mm_cols = [row[1] for row in conn.execute(text("PRAGMA table_info(mindmap_nodes)"))]
        if "x" not in mm_cols:
            conn.execute(text("ALTER TABLE mindmap_nodes ADD COLUMN x REAL"))
        if "y" not in mm_cols:
            conn.execute(text("ALTER TABLE mindmap_nodes ADD COLUMN y REAL"))
        conn.commit()


_ensure_annotation_columns()


def _migrate_mindmap_positions() -> None:
    """旧版节点拖拽以"行单位"保存 y，与新版像素单位不兼容：一次性重置为自动布局。"""
    from .models import MindmapNode, Setting
    db = SessionLocal()
    try:
        if not db.get(Setting, "mindmap_pos_units_v2"):
            db.query(MindmapNode).update({MindmapNode.x: None, MindmapNode.y: None})
            db.add(Setting(key="mindmap_pos_units_v2", value="1"))
            db.commit()
    finally:
        db.close()


_migrate_mindmap_positions()


def _relocate_pdfs() -> None:
    """数据目录迁移后，库里记录的 PDF 绝对路径可能失效：按文件名在候选目录重定位。"""
    from pathlib import Path
    from .models import Paper, Supplement
    from .services.pdf import get_pdf_dir
    db = SessionLocal()
    try:
        fixed = 0
        candidates = [config.PDF_DIR]
        try:
            candidates.append(get_pdf_dir(db))
        except Exception:
            pass
        for p in list(db.query(Paper).all()) + list(db.query(Supplement).all()):
            if not p.pdf_path:
                continue
            if not Path(p.pdf_path).exists():
                for d in candidates:
                    candidate = d / Path(p.pdf_path).name
                    if candidate.exists():
                        p.pdf_path = str(candidate)
                        fixed += 1
                        break
        if fixed:
            db.commit()
    finally:
        db.close()


_relocate_pdfs()

quit_event = threading.Event()   # start.py 的看门狗线程监听它来关停 uvicorn

app = FastAPI(title="文献管家", docs_url="/api/docs", openapi_url="/api/openapi.json")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
)

app.include_router(papers.router, prefix="/api/v1")
app.include_router(imports.router, prefix="/api/v1")
app.include_router(crossref.router, prefix="/api/v1")
app.include_router(reader.router, prefix="/api/v1")
app.include_router(annotations.router, prefix="/api/v1")
app.include_router(supplements.router, prefix="/api/v1")
app.include_router(translate.router, prefix="/api/v1")
app.include_router(ocr.router, prefix="/api/v1")
app.include_router(mindmap.router, prefix="/api/v1")
app.include_router(chat.router, prefix="/api/v1")
app.include_router(refs.router, prefix="/api/v1")


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(status_code=exc.status_code, content={"code": exc.status_code, "msg": str(exc.detail)})


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    # 422 也走统一 envelope，便于前端展示具体校验错误
    err = exc.errors()[0] if exc.errors() else {}
    loc = ".".join(str(x) for x in err.get("loc", [])[1:])
    return JSONResponse(status_code=422, content={"code": 422, "msg": f"参数校验失败：{loc} {err.get('msg', '')}"})


@app.get("/health")
def health():
    return {"code": 0, "data": "ok"}


@app.post("/api/v1/app/quit")
def quit_app():
    quit_event.set()
    return {"code": 0, "data": "quitting"}


# 静态挂载放最后（存在 index.html 才挂，测试环境无前端目录时不挂）
if (config.WEB_DIR / "index.html").exists():
    app.mount("/", StaticFiles(directory=config.WEB_DIR, html=True), name="web")
