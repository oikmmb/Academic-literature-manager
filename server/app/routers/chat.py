"""AI 对话：按文献隔离的会话，历史持久化，支持图像消息。"""
import json

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import ChatMessage, Paper
from ..services.chat_ai import chat

router = APIRouter(tags=["chat"])

MAX_IMAGE_BYTES = 4 * 1024 * 1024


class ChatIn(BaseModel):
    question: str
    image_base64: str | None = None


def _msg_out(m: ChatMessage) -> dict:
    try:
        content = json.loads(m.content)
    except Exception:
        content = {"text": m.content}
    return {"id": m.id, "role": m.role, "content": content, "created_at": m.created_at.isoformat()}


@router.get("/papers/{paper_id}/chat/messages")
def list_messages(paper_id: int, db: Session = Depends(get_db)):
    if not db.get(Paper, paper_id):
        raise HTTPException(404, "文献不存在")
    rows = db.query(ChatMessage).filter(ChatMessage.paper_id == paper_id).order_by(ChatMessage.id).all()
    return {"code": 0, "data": {"items": [_msg_out(m) for m in rows]}}


@router.delete("/papers/{paper_id}/chat/messages")
def clear_messages(paper_id: int, db: Session = Depends(get_db)):
    db.query(ChatMessage).filter(ChatMessage.paper_id == paper_id).delete()
    db.commit()
    return {"code": 0, "data": {"cleared": paper_id}}


@router.post("/papers/{paper_id}/chat")
def send_message(paper_id: int, body: ChatIn, db: Session = Depends(get_db)):
    paper = db.get(Paper, paper_id)
    if not paper:
        raise HTTPException(404, "文献不存在")
    question = body.question.strip()
    if not question:
        raise HTTPException(400, "问题不能为空")
    image = body.image_base64
    if image and len(image) > MAX_IMAGE_BYTES:
        raise HTTPException(400, "图片过大（>4MB）")

    history = [
        {"role": m.role, "content": m.content}
        for m in db.query(ChatMessage).filter(ChatMessage.paper_id == paper_id).order_by(ChatMessage.id).all()
    ]
    try:
        reply = chat(paper.title, history, question, image, db)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except httpx.HTTPError:
        raise HTTPException(502, "对话服务网络请求失败")

    user_msg = ChatMessage(paper_id=paper_id, role="user", content=json.dumps(
        {"text": question, "image": image}, ensure_ascii=False))
    ai_msg = ChatMessage(paper_id=paper_id, role="assistant", content=json.dumps(
        {"text": reply, "image": None}, ensure_ascii=False))
    db.add(user_msg)
    db.add(ai_msg)
    db.commit()
    db.refresh(ai_msg)
    return {"code": 0, "data": _msg_out(ai_msg)}
