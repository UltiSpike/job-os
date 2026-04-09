"""技能 topic 路由"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from server.storage import topics_repo

router = APIRouter(prefix="/api/v1/topics", tags=["topics"])


class TopicSet(BaseModel):
    topics: list[str]


@router.get("")
def list_topics():
    items = topics_repo.list_all()
    return {"items": [t.model_dump() for t in items]}


@router.get(":stats")
def topic_stats():
    """每个 topic 的题数 + 评分分布 — 给训练场热力图用"""
    return {"items": topics_repo.aggregate_with_stats()}


@router.get("/{topic_id}")
def get_topic(topic_id: str):
    t = topics_repo.get(topic_id)
    if not t:
        raise HTTPException(404, "topic not found")
    return t.model_dump()


# ─── question topics ───
question_router = APIRouter(prefix="/api/v1/questions", tags=["topics"])


@question_router.get("/{question_id}/topics")
def list_question_topics(question_id: str):
    items = topics_repo.list_for_question(question_id)
    return {"items": [t.model_dump() for t in items]}


@question_router.put("/{question_id}/topics")
def set_question_topics(question_id: str, body: TopicSet):
    topics_repo.set_question_topics(question_id, body.topics)
    items = topics_repo.list_for_question(question_id)
    return {"items": [t.model_dump() for t in items]}
