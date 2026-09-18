"""翻译接口 + 设置读写。"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Setting
from ..services.translate import translate as do_translate

router = APIRouter(tags=["translate", "settings"])


class TranslateIn(BaseModel):
    text: str


@router.post("/translate")
def translate_api(body: TranslateIn, db: Session = Depends(get_db)):
    try:
        result = do_translate(body.text, db)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception:
        raise HTTPException(502, "翻译服务请求失败")
    return {"code": 0, "data": result}


class SettingIn(BaseModel):
    value: str


@router.get("/settings")
def get_settings(db: Session = Depends(get_db)):
    rows = db.query(Setting).all()
    return {"code": 0, "data": {r.key: r.value for r in rows}}


@router.put("/settings/{key}")
def put_setting(key: str, body: SettingIn, db: Session = Depends(get_db)):
    row = db.get(Setting, key)
    if row:
        row.value = body.value
    else:
        db.add(Setting(key=key, value=body.value))
    db.commit()
    return {"code": 0, "data": {"key": key, "value": body.value}}
