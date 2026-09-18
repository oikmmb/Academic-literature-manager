"""Pydantic 模型（envelope：{code, data} / {code, msg}）。"""
import json
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator


class PaperIn(BaseModel):
    title: str
    authors: list[str] = Field(default_factory=list)
    first_author: str | None = None
    corresponding_author: str | None = None
    subject: str | None = None
    abstract: str | None = None
    doi: str | None = None
    journal: str | None = None
    volume: str | None = None
    issue: str | None = None
    pages: str | None = None
    year: int | None = None
    published_at: str | None = None
    source: str = "manual"


class PaperUpdate(BaseModel):
    title: str | None = None
    authors: list[str] | None = None
    first_author: str | None = None
    corresponding_author: str | None = None
    subject: str | None = None
    abstract: str | None = None
    doi: str | None = None
    journal: str | None = None
    volume: str | None = None
    issue: str | None = None
    pages: str | None = None
    year: int | None = None
    published_at: str | None = None
    source: str | None = None


class PaperOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    authors: list | None = None
    first_author: str | None = None
    corresponding_author: str | None = None
    subject: str | None = None
    abstract: str | None = None
    doi: str | None = None
    journal: str | None = None
    volume: str | None = None
    issue: str | None = None
    pages: str | None = None
    year: int | None = None
    published_at: str | None = None
    pdf_path: str | None = Field(default=None, exclude=True)   # 不外泄本地路径，仅用于计算 has_pdf
    pdf_pages: int
    source: str
    created_at: datetime
    updated_at: datetime

    @computed_field
    @property
    def has_pdf(self) -> bool:
        return bool(self.pdf_path)


class SupplementOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    paper_id: int
    label: str
    filename: str
    pdf_pages: int
    created_at: datetime


class AnnotationIn(BaseModel):
    client_id: str = Field(max_length=36)
    paper_id: int
    supp_id: int = 0
    segments: list[dict] | None = None   # 跨页锚点 [{page, ws, we}]；None=单段
    page: int = 1
    word_start: int = -1
    word_end: int = -1
    char_start: int = 0
    char_end: int = 0
    text: str = ""
    note: str = ""
    color: str | None = None
    opacity: float = 0.55
    kind: str = "highlight"


class AnnotationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    paper_id: int
    supp_id: int
    segments: list[dict] | None = None
    page: int
    word_start: int
    word_end: int
    char_start: int
    char_end: int
    text: str
    note: str
    color: str | None
    opacity: float
    kind: str
    created_at: datetime
    updated_at: datetime

    @field_validator("segments", mode="before")
    @classmethod
    def _parse_segments(cls, v):
        if isinstance(v, str):   # ORM 存 JSON 字符串
            try:
                return json.loads(v)
            except Exception:
                return None
        return v


class BatchIn(BaseModel):
    upserts: list[AnnotationIn] = Field(default_factory=list)
    deletes: list[str] = Field(default_factory=list)


class AnnotationPatch(BaseModel):
    note: str | None = None
    color: str | None = None
    opacity: float | None = Field(default=None, ge=0.1, le=1.0)
    kind: str | None = None
