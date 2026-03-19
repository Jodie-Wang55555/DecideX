"""
Cohere 精排序模块（Reranker）

使用 Cohere Rerank API 对混合检索结果进行精排，
比向量相似度更准确地评估文档与查询的匹配程度。

使用方式：
    1. 在 .env 中设置 COHERE_API_KEY=your_key
    2. 若无 API Key，自动降级为基于 TF-IDF 的本地精排

Cohere Rerank 优势：
    - 交叉编码器（Cross-encoder）架构，比双编码器更精准
    - 专门为信息检索优化
    - 支持中英文混合文本
"""

import os
import sys
from typing import List, Tuple, Optional

_ROOT = os.path.join(os.path.dirname(__file__), "..")
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from langchain_core.documents import Document


# ============================================================
# Cohere 客户端初始化
# ============================================================

COHERE_API_KEY = os.getenv("COHERE_API_KEY", "")

try:
    import cohere
    _cohere_client = cohere.Client(COHERE_API_KEY) if COHERE_API_KEY else None
    COHERE_AVAILABLE = _cohere_client is not None
except ImportError:
    _cohere_client = None
    COHERE_AVAILABLE = False
    print("[Reranker] cohere not installed. Install with: pip install cohere")


# ============================================================
# 本地降级精排（TF-IDF 相似度）
# ============================================================

def _local_rerank(
    query: str,
    documents: List[Document],
    top_k: int = 5,
) -> List[Tuple[Document, float]]:
    """
    本地精排降级方案（当无 Cohere Key 时使用）。
    基于关键词重叠度计算简单相关性分数。
    """
    import math
    import re

    def tokenize(text: str) -> set:
        return set(re.findall(r"[\u4e00-\u9fff]|[a-zA-Z0-9]+", text.lower()))

    query_tokens = tokenize(query)
    if not query_tokens:
        return [(doc, 0.5) for doc in documents[:top_k]]

    scored = []
    for doc in documents:
        doc_tokens = tokenize(doc.page_content)
        if not doc_tokens:
            scored.append((doc, 0.0))
            continue

        # Jaccard + BM25-like 长度惩罚
        intersection = query_tokens & doc_tokens
        union = query_tokens | doc_tokens
        jaccard = len(intersection) / len(union) if union else 0.0

        # 长度归一化
        length_norm = 1.0 / (1.0 + math.log(1 + len(doc_tokens)))
        score = jaccard * (1 - length_norm * 0.3)
        scored.append((doc, score))

    scored.sort(key=lambda x: x[1], reverse=True)
    return scored[:top_k]


# ============================================================
# Cohere 精排
# ============================================================

def cohere_rerank(
    query: str,
    documents: List[Document],
    top_k: int = 5,
    model: str = "rerank-multilingual-v3.0",
) -> List[Tuple[Document, float]]:
    """
    使用 Cohere Rerank API 对文档列表精排。

    Args:
        query:     检索 query
        documents: 待精排文档
        top_k:     返回 top k 文档
        model:     Cohere rerank 模型名（multilingual 支持中文）

    Returns:
        [(Document, relevance_score)] 列表，按相关性降序
    """
    if not documents:
        return []

    if not COHERE_AVAILABLE:
        print("[Reranker] Cohere unavailable, using local reranker fallback.")
        return _local_rerank(query, documents, top_k)

    try:
        texts = [doc.page_content[:512] for doc in documents]

        response = _cohere_client.rerank(
            query=query,
            documents=texts,
            top_n=min(top_k, len(texts)),
            model=model,
            return_documents=False,
        )

        results = []
        for hit in response.results:
            doc = documents[hit.index]
            doc.metadata["_cohere_score"] = round(hit.relevance_score, 4)
            results.append((doc, hit.relevance_score))

        return results

    except Exception as e:
        print(f"[Reranker] Cohere API error: {e}. Falling back to local reranker.")
        return _local_rerank(query, documents, top_k)


# ============================================================
# 主入口：精排（自动选择 Cohere 或本地）
# ============================================================

def rerank(
    query: str,
    documents: List[Document],
    top_k: int = 5,
) -> List[Document]:
    """
    对文档列表进行精排，返回最相关的 top_k 篇文档。

    自动检测 COHERE_API_KEY：
    - 有 Key → 使用 Cohere Rerank API（精准但需网络）
    - 无 Key → 使用本地 TF-IDF 精排（速度快，精度适中）

    Args:
        query:     决策问题
        documents: 检索结果文档列表
        top_k:     返回数量

    Returns:
        精排后的 Document 列表（按相关性降序）
    """
    if not documents:
        return []

    ranked = cohere_rerank(query, documents, top_k=top_k)
    return [doc for doc, _ in ranked]


def format_reranked_results(
    query: str,
    documents: List[Document],
    top_k: int = 3,
    max_chars: int = 300,
) -> str:
    """
    对检索结果精排后格式化输出，供 Agent 使用。

    Args:
        query:     决策问题（用于精排）
        documents: 原始检索文档
        top_k:     精排后保留数量
        max_chars: 每条内容截断字符数

    Returns:
        格式化的多行字符串
    """
    if not documents:
        return "（未检索到相关知识）"

    reranked = rerank(query, documents, top_k=top_k)

    lines = []
    for i, doc in enumerate(reranked, 1):
        content = doc.page_content[:max_chars]
        source = doc.metadata.get("source", doc.metadata.get("_collection", "知识库"))
        cohere_score = doc.metadata.get("_cohere_score", "")
        score_str = f"（精排分 {cohere_score:.3f}）" if cohere_score else ""
        lines.append(f"[{i}]{score_str} 来源：{source}\n{content}")

    return "\n\n---\n".join(lines)
