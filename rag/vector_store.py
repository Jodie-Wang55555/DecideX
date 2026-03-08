"""
DecideX RAG 模块 - 历史决策向量存储与检索
使用 Chroma 作为本地向量数据库，支持语义相似度搜索
"""

import os
from datetime import datetime

import chromadb
from chromadb.utils import embedding_functions

# ============================================================
# 配置
# ============================================================

# Chroma 本地持久化路径
CHROMA_PERSIST_DIR = os.path.join(
    os.path.dirname(__file__), "..", "data", "chroma_db"
)

# 相似度阈值：低于此值的结果不返回
SIMILARITY_THRESHOLD = 0.30


def _get_embedding_function():
    """
    优先使用 OpenAI Embeddings；若无 API Key 则退回本地免费模型
    本地模型：paraphrase-multilingual-MiniLM-L12-v2（支持中文，约 120MB）
    """
    api_key = os.getenv("OPENAI_API_KEY")
    if api_key:
        return embedding_functions.OpenAIEmbeddingFunction(
            api_key=api_key,
            model_name="text-embedding-ada-002",
        )
    # 本地 sentence-transformers（需要 pip install sentence-transformers）
    return embedding_functions.SentenceTransformerEmbeddingFunction(
        model_name="paraphrase-multilingual-MiniLM-L12-v2"
    )


# 单例：避免重复初始化
_collection = None


def get_collection():
    """获取（或初始化）Chroma 集合"""
    global _collection
    if _collection is None:
        os.makedirs(CHROMA_PERSIST_DIR, exist_ok=True)
        client = chromadb.PersistentClient(path=CHROMA_PERSIST_DIR)
        _collection = client.get_or_create_collection(
            name="decision_history",
            embedding_function=_get_embedding_function(),
            metadata={"hnsw:space": "cosine"},
        )
    return _collection


# ============================================================
# 写入：保存一条决策记录
# ============================================================

def save_decision(
    user_query: str,
    decision_result: str,
    cost_summary: str = "",
    risk_summary: str = "",
    value_summary: str = "",
    user_id: str = "default",
) -> str:
    """
    将完整决策记录保存到向量库。
    
    Args:
        user_query:      用户原始提问/决策场景描述
        decision_result: 最终决策结论
        cost_summary:    成本分析摘要（可选）
        risk_summary:    风险评估摘要（可选）
        value_summary:   用户价值分析摘要（可选）
        user_id:         用户标识，用于隔离不同用户的历史记录
    
    Returns:
        保存的文档 ID
    """
    collection = get_collection()

    doc_id = f"decision_{user_id}_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"

    # 向量化内容 = 场景 + 结论（决定检索质量）
    document = f"决策场景：{user_query}\n决策结论：{decision_result}"

    metadata = {
        "user_id": user_id,
        "timestamp": datetime.now().isoformat(),
        "user_query": user_query[:500],
        "cost_summary": cost_summary[:300],
        "risk_summary": risk_summary[:300],
        "value_summary": value_summary[:300],
        "decision_result": decision_result[:500],
    }

    collection.add(
        documents=[document],
        metadatas=[metadata],
        ids=[doc_id],
    )
    return doc_id


# ============================================================
# 读取：检索相似历史决策
# ============================================================

def retrieve_similar_decisions(
    query: str,
    n_results: int = 3,
    user_id: str = "default",
) -> list:
    """
    检索与当前场景最相似的历史决策记录。
    
    Args:
        query:     当前决策场景描述
        n_results: 最多返回几条
        user_id:   用户标识（只检索该用户自己的历史）
    
    Returns:
        相似度从高到低排列的历史记录列表
    """
    collection = get_collection()

    total = collection.count()
    if total == 0:
        return []

    # 按 user_id 过滤
    where = {"user_id": {"$eq": user_id}}

    try:
        results = collection.query(
            query_texts=[query],
            n_results=min(n_results, total),
            where=where,
            include=["documents", "metadatas", "distances"],
        )
    except Exception:
        return []

    decisions = []
    for i, _ in enumerate(results["documents"][0]):
        meta = results["metadatas"][0][i]
        distance = results["distances"][0][i]
        similarity = round(1 - distance, 2)  # cosine distance → similarity

        if similarity < SIMILARITY_THRESHOLD:
            continue

        decisions.append({
            "scenario":   meta.get("user_query", ""),
            "decision":   meta.get("decision_result", ""),
            "cost":       meta.get("cost_summary", ""),
            "risk":       meta.get("risk_summary", ""),
            "value":      meta.get("value_summary", ""),
            "time":       meta.get("timestamp", "")[:10],
            "similarity": similarity,
        })

    return decisions


# ============================================================
# 格式化：将历史记录转为 Prompt 文本
# ============================================================

def format_history_for_prompt(decisions: list) -> str:
    """将检索到的历史决策列表格式化为可注入 Prompt 的文本"""
    if not decisions:
        return "暂无相关历史决策记录，这是用户的第一次类似决策。"

    lines = ["📚 用户历史决策参考（相似场景，供参考偏好分析）：\n"]
    for i, d in enumerate(decisions, 1):
        lines.append(f"【历史记录 {i}】相似度 {d['similarity']}")
        lines.append(f"- 决策场景：{d['scenario']}")
        lines.append(f"- 当时结论：{d['decision']}")
        if d.get("cost"):
            lines.append(f"- 成本情况：{d['cost']}")
        if d.get("risk"):
            lines.append(f"- 风险情况：{d['risk']}")
        if d.get("value"):
            lines.append(f"- 价值评估：{d['value']}")
        lines.append(f"- 决策时间：{d['time']}\n")

    return "\n".join(lines)
