from __future__ import annotations

from dataclasses import dataclass
from typing import List
from collections import defaultdict
from sqlmodel import Session
from sred.models.core import Segment
from sred.search.fts import search_segments
from sred.search.embeddings import get_query_embedding, EMBEDDING_MODEL
from sred.search.vector_search import search_vectors
from sred.models.vector import EntityType
from sred.infra.search.vector_store import VectorStore

@dataclass
class SearchResult:
    id: int # Segment ID
    content: str
    score: float # Relevant score (sim or rank)
    source: str # e.g. "FTS", "VECTOR", "HYBRID"
    rank_fts: int = 1000
    rank_vector: int = 1000

def fts_search(session: Session, query: str, limit: int = 20) -> List[SearchResult]:
    """
    Perform FTS search.
    Returns SearchResult objects with score=1/(rank).
    """
    raw_results = search_segments(query, limit=limit)
    hits = []

    for i, row in enumerate(raw_results):
        seg_id = row[0]
        snippet = row[1]

        hits.append(SearchResult(
            id=seg_id,
            content=snippet,
            score=0, # Will be set by fusion or just rank
            source="FTS",
            rank_fts=i + 1
        ))
    return hits

def vector_search_wrapper(
    session: Session,
    query: str,
    run_id: int,
    limit: int = 20,
    vector_store: VectorStore | None = None,
) -> List[SearchResult]:
    """
    Perform Vector search.
    When *vector_store* is provided, delegates to its KNN query.
    Otherwise falls back to the legacy brute-force numpy path.
    """
    query_vec = get_query_embedding(query)

    if vector_store is not None:
        vec_results = vector_store.query(
            run_id=run_id,
            embedding_model=EMBEDDING_MODEL,
            query_vector=query_vec,
            top_k=limit,
        )
        hits: list[SearchResult] = []
        for i, qr in enumerate(vec_results):
            seg = session.get(Segment, qr.entity_id)
            if seg:
                hits.append(SearchResult(
                    id=seg.id,
                    content=(seg.content[:200] + "...") if len(seg.content) > 200 else seg.content,
                    score=qr.score,
                    source="VECTOR",
                    rank_vector=i + 1,
                ))
        return hits

    # Legacy numpy path
    vec_results_legacy = search_vectors(session, query_vec, run_id, top_k=limit)

    hits = []
    for i, (emb, score) in enumerate(vec_results_legacy):
        if emb.entity_type == EntityType.SEGMENT:
            seg = session.get(Segment, emb.entity_id)
            if seg:
                hits.append(SearchResult(
                    id=seg.id,
                    content=(seg.content[:200] + "...") if len(seg.content) > 200 else seg.content,
                    score=score,
                    source="VECTOR",
                    rank_vector=i + 1
                ))
    return hits

def rrf_fusion(fts_results: List[SearchResult], vector_results: List[SearchResult], k: int = 60) -> List[SearchResult]:
    """
    Reciprocal Rank Fusion.
    Score = 1/(k + rank_fts) + 1/(k + rank_vector)
    """
    scores = defaultdict(float)
    content_map = {}

    # Process FTS
    for res in fts_results:
        scores[res.id] += 1 / (k + res.rank_fts)
        content_map[res.id] = res.content

    # Process Vector
    for res in vector_results:
        scores[res.id] += 1 / (k + res.rank_vector)
        if res.id not in content_map:
            content_map[res.id] = res.content

    # Create fused list
    fused = []
    for seg_id, score in scores.items():
        fused.append(SearchResult(
            id=seg_id,
            content=content_map[seg_id],
            score=score,
            source="HYBRID"
        ))

    # Sort descending
    fused.sort(key=lambda x: x.score, reverse=True)
    return fused

def hybrid_search(
    session: Session,
    query: str,
    run_id: int,
    limit: int = 20,
    vector_store: VectorStore | None = None,
) -> List[SearchResult]:
    """
    Perform Hybrid Search (FTS + Vector).
    When *vector_store* is provided, the vector leg uses SqliteVecStore KNN
    instead of the legacy brute-force numpy path.
    """
    fts_hits = fts_search(session, query, limit=limit)
    vec_hits = vector_search_wrapper(session, query, run_id, limit=limit, vector_store=vector_store)

    return rrf_fusion(fts_hits, vec_hits)
