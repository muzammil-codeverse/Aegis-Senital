"""Phase 25 — ReID evaluation metrics (Rank-1, Rank-5, mAP, CMC)."""
from __future__ import annotations

import logging

from backend.app.evaluation.schemas import ReIDMetricResult

logger = logging.getLogger(__name__)


def compute_reid_metrics(
    query_embeddings: list[dict],
    gallery_embeddings: list[dict],
    top_k: list[int] | None = None,
) -> ReIDMetricResult:
    """
    Compute Rank-1, Rank-5, mAP, CMC from query/gallery embeddings.

    query_embeddings: [{"identity_id", "embedding": list[float]}]
    gallery_embeddings: [{"identity_id", "embedding": list[float]}]
    """
    import math

    warnings = []
    if top_k is None:
        top_k = [1, 5]

    if not query_embeddings or not gallery_embeddings:
        warnings.append("Insufficient embeddings for ReID evaluation")
        return ReIDMetricResult(warnings=warnings)

    def cosine_sim(a: list[float], b: list[float]) -> float:
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = math.sqrt(sum(x * x for x in a))
        norm_b = math.sqrt(sum(x * x for x in b))
        return dot / (norm_a * norm_b + 1e-9)

    # Check for overlap
    query_paths = {(q.get("image_path", ""), q["identity_id"]) for q in query_embeddings}
    gallery_paths = {(g.get("image_path", ""), g["identity_id"]) for g in gallery_embeddings}
    overlap = query_paths & gallery_paths
    if overlap:
        warnings.append(f"Overlap detected: {len(overlap)} items in both query and gallery")

    embedding_failures = sum(1 for q in query_embeddings if not q.get("embedding"))
    if embedding_failures > 0:
        warnings.append(f"{embedding_failures} query embeddings missing")

    valid_queries = [q for q in query_embeddings if q.get("embedding")]
    valid_gallery = [g for g in gallery_embeddings if g.get("embedding")]

    if not valid_queries:
        warnings.append("No valid query embeddings")
        return ReIDMetricResult(embedding_failure_count=embedding_failures, warnings=warnings)

    ranks_correct: dict[int, int] = {k: 0 for k in top_k}
    ap_list = []
    intra_dists = []
    inter_dists = []

    for query in valid_queries:
        q_emb = query["embedding"]
        q_id = query["identity_id"]

        sims = []
        for gallery in valid_gallery:
            g_emb = gallery["embedding"]
            sim = cosine_sim(q_emb, g_emb)
            sims.append((sim, gallery["identity_id"]))
            if gallery["identity_id"] == q_id:
                intra_dists.append(1.0 - sim)
            else:
                inter_dists.append(1.0 - sim)

        sims.sort(key=lambda x: x[0], reverse=True)

        # Rank-k accuracy
        for k in top_k:
            top_ids = [s[1] for s in sims[:k]]
            if q_id in top_ids:
                ranks_correct[k] += 1

        # Average Precision
        num_relevant = sum(1 for _, gid in sims if gid == q_id)
        if num_relevant > 0:
            hits = 0
            ap_sum = 0.0
            for rank, (_, gid) in enumerate(sims, 1):
                if gid == q_id:
                    hits += 1
                    ap_sum += hits / rank
            ap_list.append(ap_sum / num_relevant)

    n_queries = len(valid_queries)
    rank_1 = ranks_correct.get(1, 0) / n_queries if n_queries > 0 else None
    rank_5 = ranks_correct.get(5, 0) / n_queries if n_queries > 0 else None
    mean_ap = sum(ap_list) / len(ap_list) if ap_list else None

    cmc_curve = [{"rank": k, "accuracy": round(ranks_correct[k] / n_queries, 4)} for k in top_k]

    intra_avg = sum(intra_dists) / len(intra_dists) if intra_dists else None
    inter_avg = sum(inter_dists) / len(inter_dists) if inter_dists else None

    return ReIDMetricResult(
        rank_1=round(rank_1, 4) if rank_1 is not None else None,
        rank_5=round(rank_5, 4) if rank_5 is not None else None,
        map=round(mean_ap, 4) if mean_ap is not None else None,
        cmc_curve=cmc_curve,
        intra_identity_distance_avg=round(intra_avg, 4) if intra_avg is not None else None,
        inter_identity_distance_avg=round(inter_avg, 4) if inter_avg is not None else None,
        embedding_failure_count=embedding_failures,
        overlap_or_leakage_detected=bool(overlap),
        warnings=warnings,
    )
