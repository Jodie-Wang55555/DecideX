"""
DecideX RAG 模块 - 历史决策向量存储与检索（Multi-representation）

架构：
  每次决策结束后：
    1. 用 Gemini 提取结构化摘要（intent_label + key_factors + recommendation）
    2. Multi-representation 双表示存储：
       - 索引文档（用于向量检索）= Gemini 生成的摘要 + 偏好标签
       - 完整内容（存入 metadata）= 原始场景 + 完整分析结果
    好处：检索时用精炼摘要匹配，召回时返回完整内容，兼顾精准度和信息完整性
"""

import json
import os
import re
from datetime import datetime

import chromadb
from chromadb.utils import embedding_functions

# LLM（用于提取摘要）
try:
    from langchain_google_genai import ChatGoogleGenerativeAI
    _summary_llm = ChatGoogleGenerativeAI(model="gemini-2.5-pro", temperature=0.0)
    _LLM_AVAILABLE = True
except ImportError:
    try:
        from langchain_openai import ChatOpenAI
        _summary_llm = ChatOpenAI(model="gpt-4o", temperature=0.0)
        _LLM_AVAILABLE = True
    except ImportError:
        _summary_llm = None
        _LLM_AVAILABLE = False

from langchain_core.messages import HumanMessage, SystemMessage


# ============================================================
# Gemini 摘要提取（Multi-representation 第一步）
# ============================================================

_SUMMARY_SYSTEM = """你是一个决策摘要专家。给定一次完整的决策分析过程，提取关键信息。

输出严格 JSON，不添加任何额外文字：
{
  "intent_label": "意图类型（career_choice/investment/purchase/education/relationship/travel/general）",
  "scenario_summary": "10字以内的场景概括（如：买房vs租房决策、职业跳槽评估）",
  "key_factors": ["影响决策的3-5个关键要素"],
  "recommendation": "最终推荐方案（一句话）",
  "user_preference_tags": ["从决策中提取的用户偏好标签，如：风险规避型、成本敏感、重视稳定性"]
}"""

def extract_decision_summary(
    user_query: str,
    decision_result: str,
    cost_summary: str = "",
    risk_summary: str = "",
) -> dict:
    """
    使用 Gemini/GPT 从决策内容中提取结构化摘要（Multi-representation 索引文档）。
    
    返回的摘要用于向量化索引，使检索更精准；原始内容存入 metadata 供召回时展示。
    """
    if not _LLM_AVAILABLE or _summary_llm is None:
        return {
            "intent_label": "general",
            "scenario_summary": user_query[:20],
            "key_factors": [],
            "recommendation": decision_result[:100],
            "user_preference_tags": [],
        }

    prompt = (
        f"【用户决策问题】\n{user_query}\n\n"
        f"【最终决策结论】\n{decision_result[:400]}\n\n"
        f"【成本摘要】\n{cost_summary[:200] if cost_summary else '无'}\n\n"
        f"【风险摘要】\n{risk_summary[:200] if risk_summary else '无'}"
    )

    try:
        response = _summary_llm.invoke([
            SystemMessage(content=_SUMMARY_SYSTEM),
            HumanMessage(content=prompt),
        ])
        raw = response.content.strip()
        raw = re.sub(r"```json\s*", "", raw)
        raw = re.sub(r"```\s*", "", raw)
        return json.loads(raw)
    except Exception:
        return {
            "intent_label": "general",
            "scenario_summary": user_query[:20],
            "key_factors": [],
            "recommendation": decision_result[:100],
            "user_preference_tags": [],
        }


def build_multi_representation_doc(
    user_query: str,
    summary: dict,
) -> str:
    """
    构建 Multi-representation 索引文档。
    
    将 Gemini 提取的摘要 + 偏好标签组合成简洁的索引文本，
    用于向量化（比原始长文本更聚焦，检索更精准）。
    """
    intent = summary.get("intent_label", "general")
    scene = summary.get("scenario_summary", user_query[:20])
    factors = "、".join(summary.get("key_factors", [])[:4])
    rec = summary.get("recommendation", "")
    tags = " ".join([f"#{t}" for t in summary.get("user_preference_tags", [])[:4]])

    return (
        f"[{intent}] {scene}\n"
        f"关键要素：{factors}\n"
        f"决策结论：{rec}\n"
        f"用户偏好：{tags}"
    ).strip()

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
    # 使用 all-MiniLM-L6-v2（约 80MB，比 multilingual 版本小很多，启动更快）
    return embedding_functions.SentenceTransformerEmbeddingFunction(
        model_name="all-MiniLM-L6-v2"
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
    将决策记录以 Multi-representation 方式保存到向量库。

    Multi-representation 双表示存储：
      - 索引文档（向量化）= Gemini 提取的结构化摘要 + 用户偏好标签
        → 更聚焦，语义检索更精准
      - 完整内容（metadata）= 原始场景 + 完整分析 + 偏好标签 JSON
        → 召回时展示完整信息

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

    # ── Step 1: Gemini 提取结构化摘要 ──────────────────────────
    summary = extract_decision_summary(
        user_query=user_query,
        decision_result=decision_result,
        cost_summary=cost_summary,
        risk_summary=risk_summary,
    )

    # ── Step 2: Multi-representation 索引文档（用于向量化检索）──
    # 使用摘要而非原始长文本，使向量更聚焦于决策语义
    index_document = build_multi_representation_doc(user_query, summary)

    # ── Step 3: 完整内容存入 metadata（召回时展示）───────────────
    metadata = {
        "user_id":             user_id,
        "timestamp":           datetime.now().isoformat(),
        # 原始内容（完整版）
        "user_query":          user_query[:500],
        "decision_result":     decision_result[:500],
        "cost_summary":        cost_summary[:300],
        "risk_summary":        risk_summary[:300],
        "value_summary":       value_summary[:300],
        # Gemini 提取的结构化摘要（Multi-representation 第二个表示）
        "intent_label":        summary.get("intent_label", "general"),
        "scenario_summary":    summary.get("scenario_summary", ""),
        "recommendation":      summary.get("recommendation", ""),
        "key_factors":         json.dumps(summary.get("key_factors", []), ensure_ascii=False),
        "user_preference_tags": json.dumps(summary.get("user_preference_tags", []), ensure_ascii=False),
    }

    collection.add(
        documents=[index_document],   # 向量化的是 Gemini 摘要
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

        # 尝试解析偏好标签（Multi-representation 存储的额外字段）
        raw_tags = meta.get("user_preference_tags", "[]")
        try:
            pref_tags = json.loads(raw_tags) if isinstance(raw_tags, str) else raw_tags
            pref_tags_str = "、".join(pref_tags) if pref_tags else ""
        except Exception:
            pref_tags_str = ""

        decisions.append({
            "scenario":        meta.get("user_query", ""),
            "decision":        meta.get("decision_result", ""),
            "cost":            meta.get("cost_summary", ""),
            "risk":            meta.get("risk_summary", ""),
            "value":           meta.get("value_summary", ""),
            "time":            meta.get("timestamp", "")[:10],
            "similarity":      similarity,
            "intent_label":    meta.get("intent_label", "general"),
            "scenario_summary": meta.get("scenario_summary", ""),
            "preference_tags": pref_tags_str,
        })

    return decisions


# ============================================================
# 格式化：将历史记录转为 Prompt 文本
# ============================================================

def format_history_for_prompt(decisions: list) -> str:
    """将检索到的历史决策列表格式化为可注入 Prompt 的文本（含偏好标签）"""
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
        # 显示 Gemini 提取的偏好标签（Multi-representation 的额外收益）
        if d.get("preference_tags"):
            lines.append(f"- 用户偏好标签：{d['preference_tags']}")
        lines.append(f"- 决策时间：{d['time']}\n")

    return "\n".join(lines)
