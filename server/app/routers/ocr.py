"""图片匹配文献：剪贴板/拖入图片 → OCR → 本地模糊匹配 Top3（附 DOI 提取，供联网补录）。"""
import base64
import re

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..db import get_db
from ..services.matcher import match_local
from ..services.ocr import ocr_image

router = APIRouter(tags=["ocr"])

DOI_RE = re.compile(r"10\.\d{4,9}/[-._;()/:A-Za-z0-9]+")
MAX_IMAGE_BYTES = 10 * 1024 * 1024


class MatchIn(BaseModel):
    image_base64: str


@router.post("/ocr/match")
def ocr_match(body: MatchIn, db: Session = Depends(get_db)):
    try:
        raw = base64.b64decode(body.image_base64.split(",", 1)[-1])
    except Exception:
        raise HTTPException(400, "图片数据无效")
    if not raw:
        raise HTTPException(400, "图片为空")
    if len(raw) > MAX_IMAGE_BYTES:
        raise HTTPException(400, "图片过大（>10MB）")
    try:
        raw_text = ocr_image(raw)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except RuntimeError as e:
        raise HTTPException(502, str(e))
    if not raw_text.strip():
        return {"code": 0, "data": {"raw_text": "", "doi": None, "top3": []}}

    doi_m = DOI_RE.search(raw_text)
    top3 = match_local(db, raw_text)
    return {"code": 0, "data": {
        "raw_text": raw_text,
        "doi": doi_m.group(0).rstrip(".") if doi_m else None,
        "top3": top3,
    }}
