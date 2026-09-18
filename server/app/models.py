"""ORM 模型：papers / annotations / settings / translation_cache。"""
from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


class Paper(Base):
    """文献元数据。四个分类维度 = year / subject / first_author / corresponding_author 索引列。"""
    __tablename__ = "papers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(1000), nullable=False)
    authors: Mapped[list | None] = mapped_column(JSON, default=list)
    first_author: Mapped[str | None] = mapped_column(String(200), index=True)
    corresponding_author: Mapped[str | None] = mapped_column(String(200), index=True)
    subject: Mapped[str | None] = mapped_column(String(200), index=True)   # 主题（单值标签）
    abstract: Mapped[str | None] = mapped_column(Text)
    doi: Mapped[str | None] = mapped_column(String(200), unique=True, nullable=True)
    journal: Mapped[str | None] = mapped_column(String(500))
    volume: Mapped[str | None] = mapped_column(String(50))
    issue: Mapped[str | None] = mapped_column(String(50))
    pages: Mapped[str | None] = mapped_column(String(50))
    year: Mapped[int | None] = mapped_column(Integer, index=True)
    published_at: Mapped[str | None] = mapped_column(String(50))
    pdf_path: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    pdf_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    pdf_pages: Mapped[int] = mapped_column(Integer, default=0)
    source: Mapped[str] = mapped_column(String(20), default="manual")   # pdf_import / crossref / manual
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)


class Reference(Base):
    """文末参考文献条目：ref_num 对应正文 [N] 引用序号。"""
    __tablename__ = "references"
    __table_args__ = (Index("ix_ref_paper_num", "paper_id", "ref_num", unique=True),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    paper_id: Mapped[int] = mapped_column(Integer, ForeignKey("papers.id", ondelete="CASCADE"), index=True)
    ref_num: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text, default="")


class ChatMessage(Base):
    """AI 对话消息（按文献隔离的会话）。content 为 JSON：{"text": "...", "image": "base64..."|null}。"""
    __tablename__ = "chat_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    paper_id: Mapped[int] = mapped_column(Integer, ForeignKey("papers.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(10))   # user / assistant
    content: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class MindmapNode(Base):
    """全局笔记（思维导图）：每篇文献一棵树，parent_id=NULL 为根。"""
    __tablename__ = "mindmap_nodes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    paper_id: Mapped[int] = mapped_column(Integer, ForeignKey("papers.id", ondelete="CASCADE"), index=True)
    parent_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("mindmap_nodes.id", ondelete="CASCADE"), nullable=True,
    )
    text: Mapped[str] = mapped_column(Text, default="")
    position: Mapped[int] = mapped_column(Integer, default=0)
    x: Mapped[float | None] = mapped_column(nullable=True)   # 手动拖动后的布局坐标（NULL=自动布局）
    y: Mapped[float | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class Supplement(Base):
    """文献的补充材料（SI PDF / 附录等，一篇可挂多个）。"""
    __tablename__ = "supplements"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    paper_id: Mapped[int] = mapped_column(Integer, ForeignKey("papers.id", ondelete="CASCADE"), index=True)
    label: Mapped[str] = mapped_column(String(200), default="补充材料")
    filename: Mapped[str] = mapped_column(String(500))
    pdf_path: Mapped[str] = mapped_column(String(1000))
    pdf_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    pdf_pages: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class Annotation(Base):
    """笔记/高亮。id 为客户端 uuid（幂等批量保存）；锚点 = page + word_start/end + char_start/end。
    扫描版 PDF（无文本层）降级为 word_start=word_end=-1 的页级备注。"""
    __tablename__ = "annotations"
    __table_args__ = (Index("ix_ann_paper_page", "paper_id", "page"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    paper_id: Mapped[int] = mapped_column(Integer, ForeignKey("papers.id", ondelete="CASCADE"), index=True)
    supp_id: Mapped[int] = mapped_column(Integer, default=0)   # 0=正文；>0 = supplements.id
    segments: Mapped[str | None] = mapped_column(Text, nullable=True)   # 跨页锚点 JSON：[{page, ws, we}]；NULL=单段旧格式
    page: Mapped[int] = mapped_column(Integer, default=1)
    word_start: Mapped[int] = mapped_column(Integer, default=-1)
    word_end: Mapped[int] = mapped_column(Integer, default=-1)
    char_start: Mapped[int] = mapped_column(Integer, default=0)
    char_end: Mapped[int] = mapped_column(Integer, default=0)
    text: Mapped[str] = mapped_column(Text, default="")       # 选中原文快照
    note: Mapped[str] = mapped_column(Text, default="")
    color: Mapped[str | None] = mapped_column(String(20), nullable=True)   # NULL=纯笔记
    opacity: Mapped[float] = mapped_column(default=0.55)      # 高亮透明度 0.1~1.0
    kind: Mapped[str] = mapped_column(String(10), default="highlight")     # highlight / note / both
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)


class Setting(Base):
    """key-value 设置（DeepSeek api key 等）。"""
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[str] = mapped_column(Text, default="")


class TranslationCache(Base):
    """翻译缓存。text_hash = sha256(规范化文本 + base_url + model)，防换模型串缓存。"""
    __tablename__ = "translation_cache"

    text_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    source_text: Mapped[str] = mapped_column(Text)
    target_text: Mapped[str] = mapped_column(Text)
    model: Mapped[str] = mapped_column(String(200))
    hit_count: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
