"""匹配器：OCR 文本对库文献的模糊打分与排序。"""
from app.db import SessionLocal
from app.models import Paper
from app.services.matcher import match_local


def _seed():
    db = SessionLocal()
    db.add_all([
        Paper(title="Attention Is All You Need", first_author="Ashish Vaswani", journal="NeurIPS", year=2017, doi="10.1/a"),
        Paper(title="Deep Residual Learning for Image Recognition", first_author="Kaiming He", journal="CVPR", year=2016, doi="10.1/b"),
        Paper(title="A Survey on Graph Neural Networks", first_author="Zonghan Wu", journal="IEEE TNNLS", year=2021, doi="10.1/c"),
    ])
    db.commit()
    db.close()


def test_exact_title_hit():
    _seed()
    db = SessionLocal()
    try:
        ocr = "Deep Residual Learning for Image Recognition\nKaiming He\nMicrosoft Research\nAbstract ..."
        top3 = match_local(db, ocr)
        assert top3[0]["paper_id"] and top3[0]["title"].startswith("Deep Residual")
        assert top3[0]["match_on"] == "title"
        assert top3[0]["score"] >= 90
    finally:
        db.close()


def test_partial_title_with_ocr_noise():
    _seed()
    db = SessionLocal()
    try:
        # 模拟 OCR 噪声：大小写、断行、多余字符
        ocr = "deep residual learning for image\nrecognition * Kaiming He, et al. CVPR 2016"
        top3 = match_local(db, ocr)
        assert top3[0]["title"].startswith("Deep Residual")
        assert top3[0]["score"] >= 80
    finally:
        db.close()


def test_author_only_hit():
    _seed()
    db = SessionLocal()
    try:
        top3 = match_local(db, "Correspondence to: Ashish Vaswani, Google Brain")
        assert top3[0]["match_on"] == "first_author"
        assert top3[0]["title"] == "Attention Is All You Need"
    finally:
        db.close()


def test_no_match_empty():
    _seed()
    db = SessionLocal()
    try:
        assert match_local(db, "") == []
        # 完全无关文本 → 无结果或低分（不崩溃即可）
        res = match_local(db, "quantum entanglement teleportation paradox")
        assert all(r["score"] < 80 for r in res) or res == []
    finally:
        db.close()
