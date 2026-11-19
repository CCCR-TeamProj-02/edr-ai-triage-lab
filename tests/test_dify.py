"""Dify 연결 테스트 (3일차, TODO[DIFY-1])."""
from fastapi.testclient import TestClient

from soc.api.dify import normalize_scores
from soc.api.main import app


def test_normalize_scores():
    out = normalize_scores([{"score": 0.032}, {"score": 0.016}, {"score": 0.0}])
    assert [h["score"] for h in out] == [1.0, 0.5, 0.0]
    assert normalize_scores([{"score": 0.0}])[0]["score"] == 0.0


def test_retrieval_endpoint():
    c = TestClient(app)
    assert c.post("/dify/retrieval", json={"query": "격리"}).status_code == 403
    r = c.post("/dify/retrieval", headers={"Authorization": "Bearer change-me"},
               json={"query": "격리 승인권자", "retrieval_setting": {"top_k": 3, "score_threshold": 0.5}})
    assert r.status_code == 200
    recs = r.json()["records"]
    assert recs and recs[0]["score"] == 1.0 and recs[0]["title"].endswith(".pdf")


def test_retrieval_empty_query_returns_empty_records():
    # Dify가 API를 저장할 때 빈 검색어로 검증한다. 500이 아니라 200과 빈 결과여야 한다.
    c = TestClient(app)
    for q in ["", "   "]:
        r = c.post("/dify/retrieval", headers={"Authorization": "Bearer change-me"}, json={"query": q})
        assert r.status_code == 200 and r.json() == {"records": []}
