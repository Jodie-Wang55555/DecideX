"""
DecideX RAG 模块 - 专业知识库检索
将领域知识文档（成本规则、风险标准）向量化存入 Chroma
供 Cost Agent 和 Risk Agent 在分析时检索参考
"""

import os
from typing import Literal

import chromadb
from chromadb.utils import embedding_functions

# ============================================================
# 配置
# ============================================================

CHROMA_PERSIST_DIR = os.path.join(
    os.path.dirname(__file__), "..", "data", "chroma_db"
)

DOCUMENTS_DIR = os.path.join(os.path.dirname(__file__), "documents")

# 知识库文档映射：Collection 名称 → 文件名
KNOWLEDGE_FILES = {
    "cost":  "cost_knowledge.txt",
    "risk":  "risk_knowledge.txt",
    "value": "value_knowledge.txt",
}

# 文本分块大小（字符数）
CHUNK_SIZE = 500
CHUNK_OVERLAP = 50

# 知识库检索相似度阈值
KNOWLEDGE_THRESHOLD = 0.25


def _get_embedding_function():
    """优先 OpenAI Embeddings，无 Key 则退回本地免费模型"""
    api_key = os.getenv("OPENAI_API_KEY")
    if api_key:
        return embedding_functions.OpenAIEmbeddingFunction(
            api_key=api_key,
            model_name="text-embedding-ada-002",
        )
    return embedding_functions.SentenceTransformerEmbeddingFunction(
        model_name="paraphrase-multilingual-MiniLM-L12-v2"
    )


# 单例缓存
_client = None
_collections: dict = {}


def _get_client():
    global _client
    if _client is None:
        os.makedirs(CHROMA_PERSIST_DIR, exist_ok=True)
        _client = chromadb.PersistentClient(path=CHROMA_PERSIST_DIR)
    return _client


def _get_kb_collection(kb_type: Literal["cost", "risk"]):
    """获取指定类型的知识库 Collection（单例）"""
    if kb_type not in _collections:
        client = _get_client()
        _collections[kb_type] = client.get_or_create_collection(
            name=f"knowledge_{kb_type}",
            embedding_function=_get_embedding_function(),
            metadata={"hnsw:space": "cosine"},
        )
    return _collections[kb_type]


# ============================================================
# 文本分块工具
# ============================================================

def _chunk_text(text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list:
    """将长文本按段落+大小切分为 chunks"""
    # 优先按段落（双换行）分割，保持语义完整性
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]

    chunks = []
    current = ""
    for para in paragraphs:
        if len(current) + len(para) <= chunk_size:
            current = current + "\n\n" + para if current else para
        else:
            if current:
                chunks.append(current.strip())
            # 如果单个段落超过 chunk_size，强制按字符切分
            if len(para) > chunk_size:
                for i in range(0, len(para), chunk_size - overlap):
                    chunks.append(para[i: i + chunk_size])
            else:
                current = para

    if current:
        chunks.append(current.strip())

    return chunks


# ============================================================
# 初始化：将知识文档载入向量库
# ============================================================

def build_knowledge_index(kb_type: Literal["cost", "risk", "value"], force_rebuild: bool = False) -> int:
    """
    将知识文档分块、向量化并存入 Chroma。

    Args:
        kb_type:       知识库类型，"cost" 或 "risk"
        force_rebuild: True 则清空后重建，False 则跳过已有数据

    Returns:
        写入的 chunk 数量
    """
    collection = _get_kb_collection(kb_type)

    # 如果已有数据且不强制重建，直接跳过
    if collection.count() > 0 and not force_rebuild:
        return collection.count()

    # 如果强制重建，清空旧数据
    if force_rebuild and collection.count() > 0:
        existing = collection.get()
        if existing["ids"]:
            collection.delete(ids=existing["ids"])

    # 读取文档
    doc_file = KNOWLEDGE_FILES.get(kb_type)
    if not doc_file:
        raise ValueError(f"未知知识库类型: {kb_type}")

    doc_path = os.path.join(DOCUMENTS_DIR, doc_file)
    if not os.path.exists(doc_path):
        raise FileNotFoundError(f"知识文档不存在: {doc_path}")

    with open(doc_path, "r", encoding="utf-8") as f:
        text = f.read()

    # 分块
    chunks = _chunk_text(text)

    # 批量写入
    ids = [f"{kb_type}_chunk_{i:04d}" for i in range(len(chunks))]
    metadatas = [{"kb_type": kb_type, "chunk_index": i, "source": doc_file}
                 for i in range(len(chunks))]

    collection.add(
        documents=chunks,
        metadatas=metadatas,
        ids=ids,
    )

    return len(chunks)


def ensure_knowledge_index(kb_type: Literal["cost", "risk", "value"]) -> None:
    """确保知识库已初始化（首次运行时自动构建）"""
    collection = _get_kb_collection(kb_type)
    if collection.count() == 0:
        build_knowledge_index(kb_type)


# ============================================================
# 检索：按类型查询知识库
# ============================================================

def retrieve_knowledge(
    query: str,
    kb_type: Literal["cost", "risk", "value"],
    n_results: int = 4,
) -> list:
    """
    从指定知识库检索与 query 最相关的知识片段。

    Args:
        query:     查询文本（决策场景描述）
        kb_type:   "cost" 或 "risk"
        n_results: 最多返回几条

    Returns:
        相关知识片段列表（按相似度从高到低）
    """
    ensure_knowledge_index(kb_type)
    collection = _get_kb_collection(kb_type)

    total = collection.count()
    if total == 0:
        return []

    try:
        results = collection.query(
            query_texts=[query],
            n_results=min(n_results, total),
            include=["documents", "metadatas", "distances"],
        )
    except Exception:
        return []

    knowledge_chunks = []
    for i, doc in enumerate(results["documents"][0]):
        distance = results["distances"][0][i]
        similarity = round(1 - distance, 2)

        if similarity < KNOWLEDGE_THRESHOLD:
            continue

        knowledge_chunks.append({
            "content":    doc,
            "similarity": similarity,
            "kb_type":    kb_type,
        })

    return knowledge_chunks


def format_knowledge_for_prompt(chunks: list, kb_type: str) -> str:
    """将检索到的知识片段格式化为可注入 Prompt 的文本"""
    label_map = {"cost": "成本评估", "risk": "风险评估", "value": "用户价值"}
    label = label_map.get(kb_type, "专业")

    if not chunks:
        return f"（未检索到相关{label}知识，请基于通用专业知识进行分析）"
    lines = [f"📖 相关{label}专业知识（来自知识库，请参考以下内容进行分析）：\n"]

    for i, chunk in enumerate(chunks, 1):
        lines.append(f"【知识片段 {i}】（相似度 {chunk['similarity']}）")
        lines.append(chunk["content"])
        lines.append("")

    return "\n".join(lines)
