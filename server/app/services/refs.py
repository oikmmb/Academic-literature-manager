"""参考文献解析：定位 References 段并按 [N] / N. 切分条目。"""
import re

import fitz

HEADER_RE = re.compile(r"^\s*(References|Bibliography|REFERENCES|LITERATURE CITED)\s*:?\s*$", re.M)
BRACKET_ENTRY = re.compile(r"^\[(\d{1,3})\]\s*(.*)$", re.M)
DOT_ENTRY = re.compile(r"^(\d{1,3})\.\s+(.{20,})$", re.M)


def parse_references(pdf_path: str) -> list[tuple[int, str]]:
    """返回 [(编号, 条目文本)]，按编号升序。找不到 References 段返回空列表。"""
    doc = fitz.open(pdf_path)
    try:
        pages = [doc[i].get_text() for i in range(doc.page_count)]
    finally:
        doc.close()
    if not pages:
        return []

    # 1. 找 References 标题所在页
    start_page = None
    for i, text in enumerate(pages):
        if HEADER_RE.search(text):
            start_page = i
            break
    if start_page is None:
        # 降级：从后往前找第一个 [1] 条目（无标题的参考文献段）
        for i in range(len(pages) - 1, -1, -1):
            if re.search(r"^\s*\[1\]\s+\S", pages[i], re.M):
                start_page = i
                break
    if start_page is None:
        return []

    full = "\n".join(pages[start_page:])

    # 2. 切分条目：[N] 优先；无方括号则用 N. 行首格式
    matches = list(BRACKET_ENTRY.finditer(full))
    entry_re = BRACKET_ENTRY
    if not matches:
        matches = list(DOT_ENTRY.finditer(full))
        entry_re = DOT_ENTRY
    if not matches:
        return []

    entries: list[tuple[int, str]] = []
    for idx, m in enumerate(matches):
        num = int(m.group(1))
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(full)
        # 条目文本 = 首行剩余 + 续行（到下一个编号前）；sub 只删编号前缀保留首行内容
        body = full[m.start():end]
        body = entry_re.sub(lambda mm: mm.group(2), body, count=1)
        body = re.sub(r"\s+", " ", body).strip()
        body = body[:800]
        if body and num <= 999:
            entries.append((num, body))
    return entries
