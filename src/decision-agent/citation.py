"""
Citation 机制（决策依据溯源）

功能：
1. 将检索文档打上编号 [1][2][3]...
2. LLM 生成决策建议时在关键论点后附加引用标记
3. 决策报告中附带完整 Reference 列表，确保依据可追溯

Citation 流程：
    检索文档 → 分配 Citation ID → 注入 LLM Prompt
        ↓
    LLM 生成带 [n] 标记的回答
        ↓
    解析引用 → 附加 References 列表 → 最终决策报告
"""

import re
import json
import hashlib
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Optional
from langchain_core.documents import Document


# ============================================================
# 数据结构
# ============================================================

@dataclass
class CitationSource:
    """单个引用源"""
    cid: str                    # 引用 ID，如 "1", "2"
    content: str                # 文档内容（截断）
    source_type: str            # 来源类型: knowledge_base / memory / web_search
    collection: str             # Chroma collection 名或 URL
    relevance_score: float      # 相关性分数
    metadata: Dict = field(default_factory=dict)

    def to_reference_str(self) -> str:
        """格式化为参考文献条目"""
        type_label = {
            "knowledge_base": "📚 知识库",
            "memory": "🧠 历史记忆",
            "web_search": "🌐 网络搜索",
        }.get(self.source_type, "📄 文档")

        # 知识库：格式化集合名；网络搜索：直接显示文章标题，不做 title() 转换
        if self.source_type == "web_search":
            source_label = self.collection  # 已经是文章标题
        else:
            source_label = self.collection.replace("knowledge_", "").replace("_", " ").title()

        score_str = f"（相关度 {self.relevance_score:.2f}）" if self.relevance_score > 0 else ""

        # 网络搜索只展示标题，知识库/记忆额外显示摘要
        if self.source_type == "web_search":
            return f"[{self.cid}] {type_label} · {source_label}{score_str}"
        return (
            f"[{self.cid}] {type_label} · {source_label}{score_str}\n"
            f"    {self.content[:120]}..."
        )


@dataclass
class CitedDecision:
    """带引用的决策结果"""
    answer: str                             # 带 [n] 标记的决策建议
    references: List[CitationSource]        # 引用源列表
    intent_label: str = "general"          # 意图标签
    session_id: str = ""                   # 会话 ID

    def to_report(self) -> str:
        """生成完整决策报告（含 References）"""
        lines = [self.answer]

        if self.references:
            lines.append("\n\n---\n📎 **决策依据来源**\n")
            for ref in self.references:
                lines.append(ref.to_reference_str())

        return "\n".join(lines)

    def to_dict(self) -> dict:
        return {
            "answer": self.answer,
            "intent_label": self.intent_label,
            "session_id": self.session_id,
            "references": [asdict(r) for r in self.references],
        }


# ============================================================
# Citation Manager
# ============================================================

class CitationManager:
    """管理本次决策会话的所有引用源"""

    def __init__(self):
        self._sources: List[CitationSource] = []
        self._dedup: Dict[str, str] = {}  # content_hash → cid

    def _hash(self, content: str) -> str:
        return hashlib.md5(content[:200].encode()).hexdigest()[:8]

    def add_document(
        self,
        doc: Document,
        source_type: str = "knowledge_base",
    ) -> str:
        """
        添加文档到引用池，返回 citation ID。
        自动去重：相同内容返回已有 ID。
        """
        h = self._hash(doc.page_content)
        if h in self._dedup:
            return self._dedup[h]

        cid = str(len(self._sources) + 1)
        meta = doc.metadata or {}

        source = CitationSource(
            cid=cid,
            content=doc.page_content[:200],
            source_type=source_type,
            collection=meta.get("_collection", meta.get("source", "unknown")),
            relevance_score=float(
                meta.get("_cohere_score",
                meta.get("_rrf_score",
                meta.get("_self_rag_score", 0.0)))
            ),
            metadata=dict(meta),
        )
        self._sources.append(source)
        self._dedup[h] = cid
        return cid

    def add_documents(
        self,
        docs: List[Document],
        source_type: str = "knowledge_base",
    ) -> List[str]:
        """批量添加文档，返回 citation ID 列表"""
        return [self.add_document(doc, source_type) for doc in docs]

    def build_context_prompt(self) -> str:
        """
        生成带编号的知识上下文，注入 LLM Prompt。
        要求 LLM 在关键论点后使用 [n] 标记引用。
        """
        if not self._sources:
            return ""

        lines = [
            "【参考资料】（请在回答中用 [数字] 标注引用来源，如 [1][2]）",
            "",
        ]
        for src in self._sources:
            type_label = {
                "knowledge_base": "知识库",
                "memory": "历史记忆",
                "web_search": "网络搜索",
            }.get(src.source_type, "文档")

            lines.append(f"[{src.cid}] ({type_label}) {src.content[:250]}")
            lines.append("")

        return "\n".join(lines)

    def extract_citations_from_text(self, text: str) -> List[str]:
        """从 LLM 生成文本中提取引用的 ID 列表"""
        cited = re.findall(r"\[(\d+)\]", text)
        # 去重，保持顺序
        seen = set()
        result = []
        for c in cited:
            if c not in seen and any(s.cid == c for s in self._sources):
                seen.add(c)
                result.append(c)
        return result

    def get_cited_sources(self, text: str) -> List[CitationSource]:
        """返回文本中实际引用到的 CitationSource 列表"""
        cited_ids = set(self.extract_citations_from_text(text))
        return [s for s in self._sources if s.cid in cited_ids]

    def build_cited_decision(
        self,
        answer: str,
        intent_label: str = "general",
        session_id: str = "",
        include_all: bool = False,
    ) -> CitedDecision:
        """
        将 LLM 答案封装为带引用的 CitedDecision。

        Args:
            answer:       LLM 生成的决策建议（含 [n] 标记）
            intent_label: 意图标签
            session_id:   会话 ID
            include_all:  True = 包含所有检索源；False = 只包含实际引用的

        Returns:
            CitedDecision 对象
        """
        if include_all:
            references = self._sources
        else:
            references = self.get_cited_sources(answer)
            # 若 LLM 没有标注引用，保留 top 3
            if not references:
                references = self._sources[:3]

        return CitedDecision(
            answer=answer,
            references=references,
            intent_label=intent_label,
            session_id=session_id,
        )

    def clear(self):
        """清空引用池（新会话时调用）"""
        self._sources.clear()
        self._dedup.clear()

    @property
    def has_sources(self) -> bool:
        return len(self._sources) > 0


# ============================================================
# 便捷函数
# ============================================================

def attach_citations_to_prompt(
    base_prompt: str,
    docs: List[Document],
    source_type: str = "knowledge_base",
) -> tuple:
    """
    将文档附加到 Prompt 并返回 (增强后的prompt, CitationManager)。
    这是最简单的使用方式。

    Returns:
        (augmented_prompt, citation_manager)
    """
    manager = CitationManager()
    manager.add_documents(docs, source_type=source_type)
    context = manager.build_context_prompt()
    augmented = f"{context}\n\n{base_prompt}" if context else base_prompt
    return augmented, manager
