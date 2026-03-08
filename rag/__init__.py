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
]
