"""DecideX RAG 模块"""
from .vector_store import (
    save_decision,
    retrieve_similar_decisions,
    format_history_for_prompt,
)
from .knowledge_base import (
    build_knowledge_index,
    retrieve_knowledge,
    format_knowledge_for_prompt,
    ensure_knowledge_index,
)
from .hybrid_retrieval import (
    hybrid_retrieve,
    format_hybrid_results,
    rrf_fusion,
)
from .self_rag import (
    self_rag_filter,
    evaluate_relevance,
    evaluate_usefulness,
)
from .reranker import rerank, format_reranked_results

__all__ = [
    # 用户记忆 RAG
    "save_decision",
    "retrieve_similar_decisions",
    "format_history_for_prompt",
    # 知识库 RAG
    "build_knowledge_index",
    "ensure_knowledge_index",
    "retrieve_knowledge",
    "format_knowledge_for_prompt",
    # 混合检索 + RRF
    "hybrid_retrieve",
    "format_hybrid_results",
    "rrf_fusion",
    # Self-RAG
    "self_rag_filter",
    "evaluate_relevance",
    "evaluate_usefulness",
    # Cohere 精排
    "rerank",
    "format_reranked_results",
]
