"""RapidOCR 服务：单例懒加载（首次构造触发模型下载/初始化，之后常驻）。"""
import cv2
import numpy as np

_engine = None
_engine_error = None


def get_engine():
    """懒加载 OCR 引擎。失败信息缓存，避免每次请求重复初始化。"""
    global _engine, _engine_error
    if _engine is not None:
        return _engine
    if _engine_error:
        raise RuntimeError(_engine_error)
    try:
        from rapidocr import RapidOCR
        _engine = RapidOCR()
        return _engine
    except Exception as e:
        _engine_error = f"OCR 引擎初始化失败：{e}"
        raise


def ocr_image(image_bytes: bytes) -> str:
    """输入图片字节 → 识别的文本行（按版面顺序拼接）。"""
    arr = np.frombuffer(image_bytes, np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("无法解码图片（支持 PNG/JPG 截图）")
    engine = get_engine()
    out = engine(img)   # rapidocr 3.x 返回 RapidOCROutput 对象（含 txts/boxes/scores）
    if not out.txts:
        return ""
    lines = [str(t).strip() for t in out.txts if t and str(t).strip()]
    return "\n".join(lines)
