"""📘 4단계 저장: kb-playbooks 인덱스의 매핑을 정하고 청크를 넣습니다."""
from __future__ import annotations

from ..config import settings
from ..osclient import bulk_index, get_client


def index_body() -> dict:
    # index.knn을 켜야 벡터 검색이 됩니다. 노드가 1개라 복제본은 0, 청크가 적어 조각(shard)도 1개.
    return {
        "settings": {"index": {"knn": True, "number_of_shards": 1, "number_of_replicas": 0}},
        "mappings": {
            "properties": {
                "id": {"type": "keyword"},
                # 키워드 검색(BM25)용. 기본 분석기를 씁니다 (한국어 형태소 분석은 안 함)
                "text": {"type": "text"},
                # 벡터 검색용. 차원은 임베딩 모델과 같아야 하고, 뜻이 비슷한지는 코사인 유사도로 잰다
                "embedding": {
                    "type": "knn_vector",
                    "dimension": settings.embed_dim,
                    "method": {"name": "hnsw", "space_type": "cosinesimil", "engine": "lucene"},
                },
                # 출처 정보: 검색하지 않고 정확히 일치·표시에만 씀
                "source": {"type": "keyword"},
                "category": {"type": "keyword"},
                "page": {"type": "integer"},
                "chunk_index": {"type": "integer"},
                # 표 구조 HTML은 보관만 하고 검색 대상에서는 뺌
                "text_as_html": {"type": "text", "index": False},
            }
        },
    }


def ensure_index(client=None, recreate: bool = False) -> None:
    client = client or get_client()
    if client.indices.exists(index=settings.index_kb):
        if not recreate:
            return
        client.indices.delete(index=settings.index_kb)
    client.indices.create(index=settings.index_kb, body=index_body())


def save(records: list[dict], vectors: list[list[float]], client=None) -> int:
    client = client or get_client()
    docs = [{k: v for k, v in r.items()} | {"embedding": vec} for r, vec in zip(records, vectors, strict=True)]
    return bulk_index(client, settings.index_kb, docs, id_field="id")
