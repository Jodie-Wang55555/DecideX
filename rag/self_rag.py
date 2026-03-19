"""
Self-RAG 模块（自评估检索增强生成）

Self-RAG 核心思想：
  在将检索文档注入 LLM 之前，对检索结果打分，过滤低相关内容，
  只保留真正有助于当前决策问题的文档。

实现三个评估维度：
  1. ISREL  (文档是否相关)       → 每条文档打分，过滤低相关
  2. ISSUP  (文档是否支持答案)   → 评估文档能否支持决策论点
  3. ISUSE  (答案是否有用)       → 最终答案质量评估

性能说明：
  默认使用 Embedding 余弦相似度评分（无 LLM API 调用，毫秒级完成）。
  评分公式：cosine(query_embedding, doc_embedding)
  已复用 knowledge_base 模块的 embedding function，无额外模型加载开销。
  如需 LLM 级精度评估，可设 SELF_RAG_LLM=true（会显著增加响应时间）。
"""

import json
import re
import os
import sys
import math
import numpy as np
from typing import List, Tuple
from collections import Counter

_ROOT = os.path.join(os.path.dirname(__file__), "..")
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from langchain_core.documents import Document

# ── 是否启用 LLM 级评估（默认关闭以保证速度）──────────────────────────────────
USE_LLM_EVAL = os.getenv("SELF_RAG_LLM", "false").lower() == "true"

_llm = None

def _get_llm():
    """懒加载 LLM（只在 USE_LLM_EVAL=True 时才初始化）"""
    global _llm
    if _llm is not None:
        return _llm
    try:
        from langchain_google_genai import ChatGoogleGenerativeAI
        model = os.getenv("GOOGLE_MODEL", "gemini-2.5-flash")
        _llm = ChatGoogleGenerativeAI(model=model, temperature=0.0)
    except ImportError:
        from langchain_openai import ChatOpenAI
        _llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.0)
    return _llm


# ============================================================
# Embedding 余弦相似度评分（Self-RAG ISREL 核心实现）
# 复用 knowledge_base 的 embedding function，零额外开销
# ============================================================

_ef = None  # embedding function 懒加载

def _get_embedding_fn():
    """懒加载 embedding function（复用 knowledge_base 已加载的模型）"""
    global _ef
    if _ef is not None:
        return _ef
    try:
        from rag.knowledge_base import _get_embedding_function
        _ef = _get_embedding_function()
    except Exception:
        try:
            from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction
            model_name = os.getenv("EMBED_MODEL", "all-MiniLM-L6-v2")
            _ef = SentenceTransformerEmbeddingFunction(model_name=model_name)
        except Exception:
            _ef = None
    return _ef


def _cosine_similarity(v1: List[float], v2: List[float]) -> float:
    """计算两个向量的余弦相似度（Self-RAG ISREL 评分核心公式）"""
    a = np.array(v1, dtype=np.float32)
    b = np.array(v2, dtype=np.float32)
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(np.dot(a, b) / (norm_a * norm_b))


def _embedding_relevance_score(query: str, document: Document) -> float:
    """
    基于 Embedding 余弦相似度的相关性评分（Self-RAG ISREL 实现）。

    原理：
      score = cosine(embed(query), embed(doc))
    
    相比关键词匹配的优势：
    - 语义理解：能匹配同义词和相关概念
    - 多语言友好：中英文均有效
    - 与向量检索一致：评分与 ChromaDB 的相似度体系对齐

    无额外 API 调用，复用已加载的 sentence-transformer 模型。
    """
    ef = _get_embedding_fn()
    if ef is None:
        return _local_keyword_fallback_score(query, document)

    try:
        query_emb = ef([query])[0]
        doc_text = document.page_content[:600]
        # 优先使用文档元数据中已缓存的 embedding（避免重复计算）
        doc_emb = document.metadata.get("_cached_embedding")
        if doc_emb is None:
            doc_emb = ef([doc_text])[0]
        return _cosine_similarity(query_emb, doc_emb)
    except Exception:
        return _local_keyword_fallback_score(query, document)


def _local_keyword_fallback_score(query: str, document: Document) -> float:
    """关键词 TF 重叠评分（embedding 不可用时的降级方案）"""
    def _tokenize(text: str) -> List[str]:
        text = text.lower()
        en_words = re.findall(r'[a-z]{2,}', text)
        zh_chars = re.findall(r'[\u4e00-\u9fa5]+', text)
        zh_words = []
        for chunk in zh_chars:
            for i in range(len(chunk) - 1):
                zh_words.append(chunk[i:i+2])
            if len(chunk) >= 1:
                zh_words.append(chunk)
        return en_words + zh_words

    query_tokens = set(_tokenize(query))
    if not query_tokens:
        return 0.5

    doc_tokens = _tokenize(document.page_content[:800])
    doc_token_counts = Counter(doc_tokens)

    hit_score = sum(math.log(1 + doc_token_counts[t]) for t in query_tokens if t in doc_token_counts)
    max_possible = math.log(1 + 5) * len(query_tokens)
    score = min(hit_score / max_possible, 1.0) if max_possible > 0 else 0.0

    source = document.metadata.get("source", "")
    if any(t in source.lower() for t in query_tokens):
        score = min(score + 0.1, 1.0)
    return score


def _local_relevance_score(query: str, document: Document) -> float:
    """兼容旧接口：优先使用 embedding 相似度，降级到关键词评分"""
    return _embedding_relevance_score(query, document)


# ============================================================
# LLM 级相关性评估（慢，需 API 调用，USE_LLM_EVAL=True 时使用）
# ============================================================

_ISREL_SYSTEM = """你是一个检索质量评估专家。
给定一个用户决策问题和一段知识文本，判断该文本对回答此问题的相关性。

输出严格 JSON，不添加任何额外文字：
{
  "relevant": true 或 false,
  "score": 0到1之间的浮点数（0=完全无关，1=高度相关）,
  "reason": "一句话说明原因"
}"""

def evaluate_relevance(query: str, document: Document) -> Tuple[bool, float, str]:
    """
    ISREL：评估文档对决策问题的相关性。
    
    - USE_LLM_EVAL=False（默认）：使用本地关键词评分，速度快，无 API 消耗
    - USE_LLM_EVAL=True：使用 LLM 精确评估，质量更高但速度慢

    Returns:
        (is_relevant, score, reason)
    """
    if not USE_LLM_EVAL:
        # ── 快速本地评估路径 ───────────────────────────────────────
        score = _local_relevance_score(query, document)
        is_relevant = score >= 0.05  # 极低门槛，主要靠后续 reranker 精排
        return (is_relevant, score, "本地关键词评分")

    # ── LLM 评估路径（慢）────────────────────────────────────────
    from langchain_core.messages import HumanMessage, SystemMessage
    content = document.page_content[:600]
    prompt = f"【决策问题】\n{query}\n\n【知识文本】\n{content}"

    try:
        llm = _get_llm()
        response = llm.invoke([
            SystemMessage(content=_ISREL_SYSTEM),
            HumanMessage(content=prompt),
        ])
        raw = response.content.strip()
        raw = re.sub(r"```json\s*", "", raw)
        raw = re.sub(r"```\s*", "", raw)
        result = json.loads(raw)
        return (
            bool(result.get("relevant", False)),
            float(result.get("score", 0.0)),
            result.get("reason", ""),
        )
    except Exception:
        return (True, 0.5, "评估失败，默认保留")


# ============================================================
# 支持性评估（ISSUP）
# ============================================================

_ISSUP_SYSTEM = """你是一个证据质量评估专家。
给定一个决策问题和一段知识文本，判断该文本是否包含支持做出决策所需的具体证据或论据。

标准：
- 包含具体数据、案例、规则或分析框架 → 高支持度
- 只有模糊描述，没有具体内容 → 低支持度

输出严格 JSON，不添加任何额外文字：
{
  "supportive": true 或 false,
  "support_score": 0到1之间的浮点数,
  "key_evidence": "提炼出的关键证据（一句话）"
}"""

def evaluate_support(query: str, document: Document) -> Tuple[bool, float, str]:
    """
    ISSUP：评估文档对决策论点的支持性。
    仅在 USE_LLM_EVAL=True 且 lightweight=False 时使用。

    Returns:
        (is_supportive, support_score, key_evidence)
    """
    if not USE_LLM_EVAL:
        # 本地模式：直接通过（依赖 reranker 处理）
        return (True, 0.6, "跳过 LLM 评估")

    from langchain_core.messages import HumanMessage, SystemMessage
    content = document.page_content[:600]
    prompt = f"【决策问题】\n{query}\n\n【知识文本】\n{content}"

    try:
        llm = _get_llm()
        response = llm.invoke([
            SystemMessage(content=_ISSUP_SYSTEM),
            HumanMessage(content=prompt),
        ])
        raw = response.content.strip()
        raw = re.sub(r"```json\s*", "", raw)
        raw = re.sub(r"```\s*", "", raw)
        result = json.loads(raw)
        return (
            bool(result.get("supportive", False)),
            float(result.get("support_score", 0.0)),
            result.get("key_evidence", ""),
        )
    except Exception:
        return (True, 0.5, "")


# ============================================================
# 主函数：Self-RAG 过滤
# ============================================================

def self_rag_filter(
    query: str,
    documents: List[Document],
    rel_threshold: float = 0.5,
    sup_threshold: float = 0.3,
    max_docs: int = 3,
    lightweight: bool = True,
) -> List[Document]:
    """
    对检索结果应用 Self-RAG 过滤，只保留高质量文档。

    性能说明：
    - USE_LLM_EVAL=False（默认）：使用本地评分，无 API 调用，毫秒级完成
    - USE_LLM_EVAL=True：每篇文档调用一次 LLM，会显著增加延迟

    Args:
        query:          用户决策问题
        documents:      待过滤的文档列表
        rel_threshold:  相关性阈值（低于此值丢弃）
        sup_threshold:  支持性阈值（低于此值丢弃）
        max_docs:       最多保留文档数
        lightweight:    True = 只做相关性评估；False = 做完整 ISREL+ISSUP

    Returns:
        过滤后的高质量 Document 列表
    """
    if not documents:
        return []

    # 本地模式下降低阈值（关键词评分分布与 LLM 评分不同）
    effective_threshold = rel_threshold * 0.2 if not USE_LLM_EVAL else rel_threshold

    scored = []
    for doc in documents:
        is_rel, rel_score, rel_reason = evaluate_relevance(query, doc)

        if not is_rel or rel_score < effective_threshold:
            continue

        if not lightweight and not USE_LLM_EVAL is False:
            is_sup, sup_score, key_evidence = evaluate_support(query, doc)
            if not is_sup or sup_score < sup_threshold:
                continue
            combined = (rel_score + sup_score) / 2
            doc.metadata["_self_rag_rel"] = rel_score
            doc.metadata["_self_rag_sup"] = sup_score
            doc.metadata["_self_rag_evidence"] = key_evidence
        else:
            combined = rel_score
            doc.metadata["_self_rag_rel"] = rel_score

        doc.metadata["_self_rag_score"] = combined
        scored.append((combined, doc))

    # 按综合分数降序
    scored.sort(key=lambda x: x[0], reverse=True)

    # 若全部被过滤，返回原始文档的前 max_docs 个（保底）
    if not scored and documents:
        return documents[:max_docs]

    return [doc for _, doc in scored[:max_docs]]


# ============================================================
# ISUSE：生成质量评估（用于最终答案打分）
# ============================================================

_ISUSE_SYSTEM = """你是一个决策建议质量评估专家。
给定用户决策问题和 AI 生成的决策建议，评估该建议是否真正有帮助。

评估维度：
1. 是否直接回答了决策问题（0-3分）
2. 是否提供了具体可行的行动建议（0-3分）
3. 是否考虑了主要风险和不确定性（0-2分）
4. 逻辑是否清晰（0-2分）

总分 0-10。

输出严格 JSON，不添加任何额外文字：
{
  "useful": true 或 false（总分>=6为true）,
  "total_score": 总分（整数 0-10）,
  "feedback": "一句话评价，若有不足指出改进方向"
}"""

def evaluate_usefulness(query: str, answer: str) -> dict:
    """
    ISUSE：评估最终决策建议的质量。
    仅在 USE_LLM_EVAL=True 时调用 LLM，否则返回默认值。

    Returns:
        {"useful": bool, "total_score": int, "feedback": str}
    """
    if not USE_LLM_EVAL:
        return {"useful": True, "total_score": 7, "feedback": "本地模式跳过质量评估"}

    from langchain_core.messages import HumanMessage, SystemMessage
    prompt = f"【决策问题】\n{query}\n\n【AI决策建议】\n{answer[:800]}"

    try:
        llm = _get_llm()
        response = llm.invoke([
            SystemMessage(content=_ISUSE_SYSTEM),
            HumanMessage(content=prompt),
        ])
        raw = response.content.strip()
        raw = re.sub(r"```json\s*", "", raw)
        raw = re.sub(r"```\s*", "", raw)
        return json.loads(raw)
    except Exception:
        return {"useful": True, "total_score": 6, "feedback": "评估失败"}
