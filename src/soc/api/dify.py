"""Dify 외부 지식(External Knowledge API) 연결: Dify가 📘 플레이북 검색을 부를 수 있게 합니다. (3일차)

Dify 요청: POST /dify/retrieval
    {"knowledge_id": "...", "query": "...", "retrieval_setting": {"top_k": 3, "score_threshold": 0.5}}
    헤더 Authorization: Bearer <DIFY_API_KEY>
응답: {"records": [{"content", "score"(0~1), "title", "metadata"}]}
"""
from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from ..config import settings

router = APIRouter()


class RetrievalSetting(BaseModel):
    top_k: int = 3
    score_threshold: float = 0.0


class RetrievalRequest(BaseModel):
    knowledge_id: str = ""
    query: str
    retrieval_setting: RetrievalSetting = Field(default_factory=RetrievalSetting)


def normalize_scores(hits: list[dict]) -> list[dict]:
    """우리 검색 점수(RRF 등)를 Dify가 쓰는 0~1 범위로 바꿉니다."""
    # 왜 그냥 쓰면 안 될까요? RRF 점수는 1/61 ≈ 0.016 근처라 Dify의 score_threshold(예: 0.5)에 모두 걸러집니다.
    max_score = max((hit["score"] for hit in hits), default=0)
    return [
        {**hit, "score": hit["score"] / max_score if max_score else 0.0}
        for hit in hits
    ]


@router.post("/dify/retrieval")
def retrieval(req: RetrievalRequest, authorization: str = Header(default="")):
    if authorization != f"Bearer {settings.dify_api_key}":
        raise HTTPException(status_code=403, detail={"error_code": 1002, "error_msg": "인증 실패"})
    # Dify는 External Knowledge API를 저장할 때 빈 검색어로 검증 요청을 보냅니다.
    # 빈 글을 임베딩하면 OpenAI가 400을 내서 500이 되므로, 검색하지 않고 빈 결과를 돌려줍니다.
    if not req.query.strip():
        return {"records": []}
    from ..agent.toolset import search_playbook_fn

    hits = normalize_scores(search_playbook_fn()(req.query, req.retrieval_setting.top_k))
    records = [{"content": h["text"], "score": h["score"], "title": h.get("source") or "",
                "metadata": {"source": h.get("source"), "page": h.get("page"), "category": h.get("category")}}
               for h in hits if h["score"] >= req.retrieval_setting.score_threshold]
    return {"records": records}
