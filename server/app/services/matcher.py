"""图片匹配：OCR 全文对库中文献的标题/第一作者/期刊做模糊匹配。"""
import re

from rapidfuzz import fuzz
from sqlalchemy.orm import Session

from ..models import Paper


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s.lower()).strip()


def match_local(db: Session, ocr_text: str, limit: int = 3) -> list[dict]:
    """返回 Top N：[{paper_id, title, score, match_on}]。score = partial/token_set 双算法取大。"""
    ocr_n = _norm(ocr_text)
    if not ocr_n:
        return []
    scored = []
    for p in db.query(Paper).all():
        best, field = 0, ""
        for name, val in (("title", p.title), ("first_author", p.first_author or ""), ("journal", p.journal or "")):
            if not val:
                continue
            val_n = _norm(val)
            s = max(fuzz.partial_ratio(ocr_n, val_n), fuzz.token_set_ratio(ocr_n, val_n))
            if s > best:
                best, field = s, name
        if best > 0:
            scored.append((best, p, field))
    scored.sort(key=lambda t: -t[0])
    return [
        {"paper_id": p.id, "title": p.title, "score": int(s), "match_on": f, "year": p.year}
        for s, p, f in scored[:limit]
    ]
