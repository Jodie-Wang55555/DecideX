"""
混合检索模块（Hybrid Retrieval）

实现 BM25 关键词检索 + 向量语义检索，通过 RRF（Reciprocal Rank Fusion）
融合两路结果，提升召回率和精准度。

架构：
    Query
      ├─ BM25 关键词检索 → 候选列表A（按 BM25 分数排序）
      └─ 向量语义检索   → 候选列表B（按余弦相似度排序）
              ↓
        RRF 融合排序（Reciprocal Rank Fusion）
              ↓
        统一候选文档（含来源标记）
              ↓
        (可选) Cohere 精排 / Self-RAG 过滤
"""

import os
import sys
from typing import List, Optional, Tuple

# 确保能找到上层模块
_ROOT = os.path.join(os.path.dirname(__file__), "..")
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import chromadb
from langchain_core.documents import Document

# ============================================================
# BM25 依赖（rank_bm25）
# ============================================================
try:
    from rank_bm25 import BM25Okapi
    BM25_AVAILABLE = True
except ImportError:
    BM25_AVAILABLE = False
    print("[HybridRetrieval] rank_bm25 not installed, falling back to vector-only search. "
          "Install with: pip install rank-bm25")

# ============================================================
# ChromaDB 向量检索（复用 knowledge_base 的客户端和 embedding）
# ============================================================
from rag.knowledge_base import _get_client, _get_embedding_function as _get_kb_ef

def _get_collection(collection_name: str):
    """通用 Chroma Collection 获取器（按名称）"""
    client = _get_client()
    ef = _get_kb_ef()
    return client.get_or_create_collection(
        name=collection_name,
        embedding_function=ef,
        metadata={"hnsw:space": "cosine"},
    )

def _get_embedding_function():
    return _get_kb_ef()


# ============================================================
# RRF 融合算法
# ============================================================

def rrf_fusion(
    ranked_lists: List[List[Tuple[str, float]]],
    k: int = 60,
) -> List[Tuple[str, float]]:
    """
    Reciprocal Rank Fusion（RRF）

    Args:
        ranked_lists: 多个排序列表，每个列表元素为 (doc_id, score)
        k:            RRF 常数（防止排名靠前的结果过于主导，默认 60）

    Returns:
        融合后的 (doc_id, rrf_score) 列表，按 rrf_score 降序
    """
    scores: dict = {}
    for ranked in ranked_lists:
        for rank, (doc_id, _) in enumerate(ranked, start=1):
            scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (k + rank)

    return sorted(scores.items(), key=lambda x: x[1], reverse=True)


# ============================================================
# BM25 检索器
# ============================================================

class BM25Retriever:
    """基于 rank_bm25 的关键词检索器"""

    def __init__(self, documents: List[Document]):
        """
        Args:
            documents: LangChain Document 列表
        """
        self.documents = documents
        if not BM25_AVAILABLE:
            self.bm25 = None
            return

        # 分词（简单空格 + 中文字符级别切分）
        tokenized_corpus = [self._tokenize(d.page_content) for d in documents]
        self.bm25 = BM25Okapi(tokenized_corpus)

    def _tokenize(self, text: str) -> List[str]:
        """简单分词：英文按空格，中文按字符"""
        import re
        # 保留中文字和英文词
        tokens = []
        for token in re.findall(r"[\u4e00-\u9fff]|[a-zA-Z0-9]+", text.lower()):
            tokens.append(token)
        return tokens if tokens else [text]

    def retrieve(self, query: str, top_k: int = 5) -> List[Tuple[str, float]]:
        """
        Returns:
            (doc_index_as_str, bm25_score) 列表
        """
        if self.bm25 is None or not self.documents:
            return []

        query_tokens = self._tokenize(query)
        scores = self.bm25.get_scores(query_tokens)

        # 取 top_k
        indexed = sorted(enumerate(scores), key=lambda x: x[1], reverse=True)[:top_k]
        return [(str(i), score) for i, score in indexed]


# ============================================================
# 向量检索器（封装 ChromaDB）
# ============================================================

def vector_retrieve(
    collection_name: str,
    query: str,
    top_k: int = 5,
) -> Tuple[List[Document], List[Tuple[str, float]]]:
    """
    从指定 Chroma collection 进行向量检索。

    Returns:
        (documents, ranked_list)
        ranked_list: [(doc_id, distance_score)]，score 越高越相似
    """
    try:
        col = _get_collection(collection_name)
        ef = _get_kb_ef()

        # ChromaDB EmbeddingFunction 是 callable: ef(["text"]) → [[float...]]
        query_embedding = ef([query])[0]
        results = col.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
            include=["documents", "metadatas", "distances"],
        )

        docs = []
        ranked = []
        if results and results["documents"] and results["documents"][0]:
            for doc_text, meta, distance in zip(
                results["documents"][0],
                results["metadatas"][0],
                results["distances"][0],
            ):
                doc = Document(
                    page_content=doc_text,
                    metadata={**meta, "_collection": collection_name, "_distance": distance},
                )
                docs.append(doc)
                # Chroma 返回的是 L2 距离，越小越相似；转为相似度分数
                sim_score = 1.0 / (1.0 + distance)
                ranked.append((doc_text[:40], sim_score))  # 用内容前缀做 key

        return docs, ranked

    except Exception as e:
        print(f"[HybridRetrieval] vector_retrieve error for {collection_name}: {e}")
        return [], []


# ============================================================
# 主入口：混合检索
# ============================================================

def hybrid_retrieve(
    collection_name: str,
    query: str,
    top_k: int = 5,
    bm25_weight: float = 0.4,
    vector_weight: float = 0.6,
    rrf_k: int = 60,
    all_documents: Optional[List[Document]] = None,
) -> List[Document]:
    """
    混合检索主函数：BM25 + 向量检索，通过 RRF 融合。

    Args:
        collection_name: Chroma collection 名称
        query:           检索 query
        top_k:           最终返回文档数
        bm25_weight:     BM25 权重（当前 RRF 不需要，保留供扩展）
        vector_weight:   向量检索权重
        rrf_k:           RRF 常数
        all_documents:   若提供，则 BM25 在此列表上检索；否则用向量检索结果

    Returns:
        融合后的 Document 列表（按相关性降序）
    """
    # --- 向量检索 ---
    vector_docs, vector_ranked = vector_retrieve(collection_name, query, top_k=top_k * 2)

    if not BM25_AVAILABLE or not vector_docs:
        # 降级：仅向量检索
        return vector_docs[:top_k]

    # --- BM25 检索 ---
    source_docs = all_documents if all_documents else vector_docs
    bm25_retriever = BM25Retriever(source_docs)
    bm25_ranked_raw = bm25_retriever.retrieve(query, top_k=top_k * 2)

    # 统一 doc_id 映射：BM25 用 index，向量用内容前缀 → 都映射到 Document
    # 构建索引：content_prefix → Document
    doc_map: dict = {}
    for doc in vector_docs:
        key = doc.page_content[:40]
        doc_map[key] = doc
    for i, doc in enumerate(source_docs):
        doc_map[str(i)] = doc

    # BM25 ranked 的 key 是 str(index)，需映射到内容前缀
    bm25_ranked_unified = []
    for idx_str, score in bm25_ranked_raw:
        idx = int(idx_str)
        if idx < len(source_docs):
            key = source_docs[idx].page_content[:40]
            bm25_ranked_unified.append((key, score))

    # --- RRF 融合 ---
    fused = rrf_fusion([vector_ranked, bm25_ranked_unified], k=rrf_k)

    # 按 RRF 分数顺序取 top_k
    result_docs = []
    seen = set()
    for key, rrf_score in fused[:top_k * 2]:
        if key in doc_map and key not in seen:
            doc = doc_map[key]
            doc.metadata["_rrf_score"] = round(rrf_score, 6)
            result_docs.append(doc)
            seen.add(key)
        if len(result_docs) >= top_k:
            break

    return result_docs


# ============================================================
# 格式化输出
# ============================================================

def format_hybrid_results(docs: List[Document], max_chars: int = 300) -> str:
    """将检索结果格式化为 Agent 可读字符串"""
    if not docs:
        return "（未检索到相关知识）"

    lines = []
    for i, doc in enumerate(docs, 1):
        content = doc.page_content[:max_chars]
        source = doc.metadata.get("source", doc.metadata.get("_collection", "知识库"))
        rrf_score = doc.metadata.get("_rrf_score", "")
        score_str = f"（相关度 {rrf_score:.4f}）" if rrf_score else ""
        lines.append(f"[{i}] {score_str} 来源：{source}\n{content}")

    return "\n\n---\n".join(lines)
