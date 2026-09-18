"""PyMuPDF 服务：元数据提取、PDF 哈希、页 PNG 渲染缓存、词级文本提取。"""
import hashlib
import re
from pathlib import Path

import fitz

from ..config import CACHE_DIR, PDF_DIR, RENDER_DPI

DOI_RE = re.compile(r"10\.\d{4,9}/[-._;()/:A-Za-z0-9]+")
YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")


def get_pdf_dir(db=None) -> Path:
    """文献 PDF 保存目录：设置页配置（settings.pdf_dir）优先，否则默认 PDF_DIR。"""
    custom = None
    if db is not None:
        try:
            from ..models import Setting
            row = db.get(Setting, "pdf_dir")
            if row and row.value.strip():
                custom = Path(row.value.strip())
        except Exception:
            custom = None
    target = custom or PDF_DIR
    target.mkdir(parents=True, exist_ok=True)
    return target


def pdf_hash(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _strip_jats(text: str) -> str:
    """Crossref 摘要常带 <jats:p> 标签，粗清洗。"""
    return re.sub(r"<[^>]+>", " ", text).replace("\n", " ").strip()


def _guess_title(doc: fitz.Document) -> str:
    """优先 PDF 内嵌元数据标题；否则取首页字号最大文本块的首行。"""
    meta = doc.metadata or {}
    if meta.get("title"):
        return meta["title"].strip()
    if doc.page_count > 0:
        page = doc[0]
        blocks = [b for b in page.get_text("blocks") if b[6] == 0 and b[4].strip()]
        if blocks:
            blocks.sort(key=lambda b: (-b[3], b[1]))  # 字号大优先
            lines = [ln.strip() for ln in blocks[0][4].splitlines() if ln.strip()]
            if lines:
                return lines[0][:500]
    return ""


def _find_abstract(doc: fitz.Document) -> str:
    """启发式：前 3 页里 Abstract 与 Introduction/Keywords 之间的文本。"""
    for pno in range(min(3, doc.page_count)):
        text = doc[pno].get_text()
        m = re.search(r"\bAbstract\b", text, re.IGNORECASE)
        if not m:
            continue
        rest = text[m.end():]
        end = re.search(r"\b(Introduction|Keywords|1\.?\s*Introduction)\b", rest, re.IGNORECASE)
        abstract = rest[: end.start()] if end else rest[:2000]
        return re.sub(r"\s+", " ", abstract).strip()[:3000]
    return ""


def extract_metadata(path: Path) -> dict:
    """打开 PDF 提取规范化元数据。启发式结果仅作初填，用户在确认表单修正。"""
    doc = fitz.open(path)
    try:
        meta = doc.metadata or {}
        raw_authors = meta.get("author", "")
        # "Lastname, Firstname; Lastname2, Firstname2" 转成 "Firstname Lastname"
        authors = []
        for part in re.split(r"[;,]", raw_authors):
            part = part.strip()
            if not part:
                continue
            if "," in part:
                last, _, first = part.partition(",")
                part = f"{first.strip()} {last.strip()}"
            authors.append(part)
        authors = [a for a in authors if a]

        first_text = doc[0].get_text() if doc.page_count > 0 else ""
        doi_m = DOI_RE.search(first_text) or DOI_RE.search(meta.get("doi", "") or "")
        year_m = YEAR_RE.search(first_text)
        year = int(year_m.group(0)) if year_m else None
        if meta.get("creationDate"):
            m2 = YEAR_RE.search(meta["creationDate"])
            year = year or (int(m2.group(0)) if m2 else None)

        return {
            "title": _guess_title(doc),
            "authors": authors,
            "first_author": authors[0] if authors else None,
            "corresponding_author": None,   # PDF 无法可靠识别，交用户确认
            "year": year,
            "journal": None,   # 期刊名无法从 PDF 可靠提取，交 Crossref 补全或用户填写
            "doi": doi_m.group(0).rstrip(".") if doi_m else None,
            "abstract": _find_abstract(doc) or None,
            "page_count": doc.page_count,
        }
    finally:
        doc.close()


# ---------------- 阅读器：页渲染 + 词提取（M3 使用） ----------------

def page_image_path(doc_key: str, page: int, content_hash: str = "", dpi: int = RENDER_DPI) -> Path:
    """doc_key：p{paper_id}（正文）或 s{supp_id}（补充材料）。
    content_hash = PDF 内容指纹（防 id 复用/文件替换后命中旧缓存串档）。"""
    tag = f"_{content_hash[:8]}" if content_hash else ""
    return CACHE_DIR / f"{doc_key}{tag}_{page}@{dpi}.png"


def render_page_png(doc_key: str, page: int, pdf_path: str, content_hash: str = "", dpi: int = RENDER_DPI) -> Path:
    """渲染单页 PNG，磁盘缓存；返回缓存文件路径。dpi 档位 150/300/600。"""
    cached = page_image_path(doc_key, page, content_hash, dpi)
    if cached.exists():
        return cached
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    doc = fitz.open(pdf_path)
    try:
        pix = doc[page - 1].get_pixmap(dpi=dpi)
        pix.save(cached)
    finally:
        doc.close()
    return cached


def _classify_zones(words: list[dict]) -> None:
    """页眉页脚检测：按行间隙找正文主体块，块外为 header/footer（就地写 zone 字段）。
    正文块 = 行间无大间隙（> 中位行高×2.5）的最大连续行簇。"""
    if not words:
        return
    # 行聚类（y 容差 3pt 顺序合并）
    rows: list[dict] = []
    for w in sorted(words, key=lambda x: x["y"]):
        if rows and abs(w["y"] - rows[-1]["y"]) <= 3:
            rows[-1]["h"] = max(rows[-1]["h"], w["h"])
            rows[-1]["y"] = min(rows[-1]["y"], w["y"])
        else:
            rows.append({"y": w["y"], "h": w["h"], "count": 1})
    if len(rows) == 1:
        for w in words:
            w["zone"] = "body"
        return
    heights = sorted(r["h"] for r in rows)
    gap_th = (heights[len(heights) // 2] or 10) * 2.5
    # 最大连续行块（间隙 <= gap_th）
    best_s, best_e, best_len = 0, 0, 0
    s = 0
    for i in range(1, len(rows)):
        gap = rows[i]["y"] - (rows[i - 1]["y"] + rows[i - 1]["h"])
        if gap > gap_th:
            if i - s > best_len:
                best_s, best_e, best_len = s, i, i - s
            s = i
    if len(rows) - s > best_len:
        best_s, best_e, best_len = s, len(rows), len(rows) - s
    top_y = rows[best_s]["y"] - 1
    bot_y = rows[best_e - 1]["y"] + rows[best_e - 1]["h"] + 1
    for w in words:
        if w["y"] + w["h"] <= top_y:
            w["zone"] = "header"
        elif w["y"] >= bot_y:
            w["zone"] = "footer"
        else:
            w["zone"] = "body"


def words_for_page(pdf_path: str, page: int) -> dict:
    """词级数据：与渲染 PNG 同一 PDF 点坐标系（原点左上）。含 zone 标记（header/body/footer）。"""
    doc = fitz.open(pdf_path)
    try:
        p = doc[page - 1]
        raw = p.get_text("words")   # (x0, y0, x1, y1, word, block, line, word_no)
        words = [
            {
                "i": idx, "t": w[4],
                "x": round(w[0], 2), "y": round(w[1], 2),
                "w": round(w[2] - w[0], 2), "h": round(w[3] - w[1], 2),
                "b": w[5], "l": w[6],
            }
            for idx, w in enumerate(raw)
        ]
        _classify_zones(words)
        return {
            "page": page,
            "page_count": doc.page_count,
            "size": {"w": round(p.rect.width, 2), "h": round(p.rect.height, 2)},
            "words": words,
        }
    finally:
        doc.close()
