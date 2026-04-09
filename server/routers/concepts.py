"""Concept layer routes — /concepts"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from server.services import mastery_service
from server.storage import concepts_repo

router = APIRouter(prefix="/api/v1/concepts", tags=["concepts"])


@router.get("")
def list_concepts(track: str | None = None):
    return {"items": concepts_repo.list_concepts(track)}


@router.get("/{slug}")
def get_concept(slug: str):
    c = concepts_repo.get_concept(slug)
    if not c:
        raise HTTPException(404, "concept not found")
    c["question_ids"] = concepts_repo.list_questions_for_concept(slug)
    c["mastery"] = mastery_service.compute_mastery_for_concept(slug)
    return c


@router.get("/{slug}/mastery")
def get_concept_mastery(slug: str):
    return mastery_service.compute_mastery_for_concept(slug)
