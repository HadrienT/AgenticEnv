from __future__ import annotations

from kbase.retrieval.fusion import RankedHit, rank_single_branch, reciprocal_rank_fusion


def test_rrf_boosts_chunks_present_in_both_branches() -> None:
    vector_hits = [RankedHit("a", 0.1), RankedHit("b", 0.2)]
    lexical_hits = [RankedHit("b", 5.0), RankedHit("c", 4.0)]

    fused = reciprocal_rank_fusion(vector_hits, lexical_hits, rrf_k=60)

    assert fused["a"]["vector"] == 0.1
    assert "lexical" not in fused["a"]
    assert fused["b"]["vector"] == 0.2
    assert fused["b"]["lexical"] == 5.0
    # b appears rank-2 in vector and rank-1 in lexical: it must outrank a (rank-1 vector only)
    # and c (rank-2 lexical only).
    assert fused["b"]["fused"] > fused["a"]["fused"]
    assert fused["b"]["fused"] > fused["c"]["fused"]


def test_rrf_score_formula() -> None:
    fused = reciprocal_rank_fusion([RankedHit("a", 1.0)], [], rrf_k=60)
    assert fused["a"]["fused"] == 1.0 / (60 + 1)


def test_rank_single_branch_vector_preserves_order() -> None:
    hits = [RankedHit("a", 0.1), RankedHit("b", 0.2)]
    fused = rank_single_branch(hits, "vector")
    assert fused["a"]["fused"] > fused["b"]["fused"]
    assert fused["a"]["vector"] == 0.1
