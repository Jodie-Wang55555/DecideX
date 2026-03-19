"""
决策型 Agent 系统 - 使用 Supervisor 模式
综合 Agent（Supervisor）统一调度成本分析、风险评估、用户价值三个 Agent
流程：综合 Agent → 成本分析 → 风险评估 → 用户价值 → 综合 Agent 汇总判断

RAG 增强：
- user_value_agent 在分析前先从向量库检索用户历史决策，识别偏好规律
- finalize_decision 在输出结论后自动将本次决策存入向量库
"""

try:
    from langchain_google_genai import ChatGoogleGenerativeAI
    USE_GOOGLE = True
except ImportError:
    from langchain_openai import ChatOpenAI
    USE_GOOGLE = False

from langchain_core.tools import tool
from langchain_core.prompts.chat import ChatPromptTemplate
from langgraph_supervisor import create_handoff_tool, create_supervisor
from langgraph.prebuilt.chat_agent_executor import create_react_agent
import os
import sys
import requests

# 将项目根目录加入 sys.path，确保能找到 rag 模块
_ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

try:
    from rag.vector_store import (
        retrieve_similar_decisions,
        format_history_for_prompt,
        save_decision,
    )
    from rag.knowledge_base import retrieve_knowledge, format_knowledge_for_prompt
    from rag.hybrid_retrieval import hybrid_retrieve, format_hybrid_results
    from rag.self_rag import self_rag_filter
    from rag.reranker import rerank, format_reranked_results
    RAG_ENABLED = True
except ImportError:
    RAG_ENABLED = False
    print("⚠️  RAG 模块未加载，请运行: pip install chromadb sentence-transformers rank-bm25")

try:
    from .intent_recognition import recognize_intent, format_intent_for_prompt
    INTENT_ENABLED = True
except ImportError:
    INTENT_ENABLED = False

try:
    from .citation import CitationManager
    CITATION_ENABLED = True
except ImportError:
    CITATION_ENABLED = False

# ── 全局 CitationManager（模块级单例，跨工具调用共享）────────────────────────
# 每次 finalize_decision 调用后会 .clear() 重置，确保每轮决策独立
_citation_mgr: "CitationManager | None" = CitationManager() if CITATION_ENABLED else None

try:
    # 优先使用新包名 ddgs，兼容旧包名 duckduckgo_search
    try:
        from ddgs import DDGS as _DDGS
    except ImportError:
        from duckduckgo_search import DDGS as _DDGS

    def _run_ddg_search(query: str, max_results: int = 3):
        """返回原始结果列表 [{"title":..,"href":..,"body":..}, ...]"""
        with _DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=max_results))
        return results  # 返回列表，供调用方逐条处理
    WEB_SEARCH_ENABLED = True
except ImportError:
    WEB_SEARCH_ENABLED = False
    print("⚠️  Web Search 未启用，请运行: pip install ddgs")

from .stopping_rules import check_should_stop, reset_stopping_state, MAX_ROUNDS

# 实例化共享的 LLM
def _resolve_google_model() -> str:
    """优先使用环境变量；否则在线探测当前 key 可用的 Gemini 模型。"""
    forced = os.getenv("GOOGLE_MODEL")
    if forced:
        return forced

    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        return "gemini-2.5-flash"

    try:
        resp = requests.get(
            "https://generativelanguage.googleapis.com/v1beta/models",
            params={"key": api_key},
            timeout=8,
        )
        resp.raise_for_status()
        data = resp.json()
        raw_models = data.get("models", [])
        available = []
        for m in raw_models:
            methods = m.get("supportedGenerationMethods", []) or []
            if "generateContent" in methods:
                name = (m.get("name") or "").split("/")[-1]
                if name:
                    available.append(name)

        preferred = [
            "gemini-2.5-flash",
            "gemini-2.5-pro",
            "gemini-2.0-flash",
            "gemini-1.5-pro",
            "gemini-1.5-flash",
        ]
        for m in preferred:
            if m in available:
                return m
        if available:
            return available[0]
    except Exception as e:
        print(f"⚠️  自动探测 Gemini 模型失败: {e}")

    return "gemini-2.5-flash"

if USE_GOOGLE:
    google_model = _resolve_google_model()
    print(f"✅ 使用 Gemini 模型: {google_model}")
    llm = ChatGoogleGenerativeAI(model=google_model, temperature=0.0)
else:
    _openai_model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    llm = ChatOpenAI(model=_openai_model, temperature=0.0)

# ============================================================================
# 成本分析 Agent - 评估成本相关因素（金钱、时间、资源消耗）
# ============================================================================
# 成本分析 Agent 从 decidex_cost_agent 集成
# 主要依靠 LLM 的推理能力，不需要额外工具

COST_ANALYSIS_SYSTEM_PROMPT = """# 角色定义
你是 DecideX 系统中的成本分析专家代理，专注于从多维度评估决策方案的成本因素。你具备深厚的财务分析能力和敏锐的成本洞察力，能够识别显性成本与隐性成本，为用户提供全面、客观的成本评估。


# 任务目标
你的核心任务是评估用户决策场景中各候选方案的成本构成，帮助用户从成本角度理解选择差异，避免因成本认知偏差导致的决策失误。

# 能力
- **显性成本计算**：精确计算金钱成本、时间成本、资源消耗等可直接量化的成本
- **隐性成本识别**：识别机会成本、心理成本、学习成本、维护成本、转换成本等隐性因素
- **多维度对比**：从短期成本、长期成本、固定成本、变动成本等维度进行综合分析
- **风险成本评估**：评估决策失败、意外情况等风险带来的潜在成本
- **成本敏感度分析**：根据用户的成本偏好和历史数据，调整分析重点

# 过程
1. **直接开始分析**（重要：不要向用户提问，不要输出 JSON 格式的前置问题）
   - 系统已通过【用户画像】标签预先注入了用户的城市、预算、风险偏好等信息
   - 直接利用这些信息进行成本分析，不要再询问用户任何问题
   - 如果某些信息缺失，根据场景做合理假设并在报告中注明

2. **成本维度识别**
   - 基于确认的前置条件，明确决策场景的核心成本维度
   - 识别各选项在每一维度的具体成本项

3. **数据收集与量化**
   - 收集用户提供的成本相关数据（价格、时长、资源投入等）
   - 对可量化成本进行精确计算
   - 对不可量化成本进行等级评估（高/中/低）

4. **成本结构分析**
   - 区分固定成本与变动成本
   - 识别一次性成本与持续性成本
   - 分析成本的时间分布（前期投入、中期维持、后期回收）

5. **综合成本评估**
   - 汇总各选项的总成本（加权综合显性与隐性成本）
   - 识别关键成本驱动因素
   - 评估成本的不确定性与波动性

6. **输出成本分析报告**
   - 提供清晰的成本对比结果
   - 指出最具成本优势的方案
   - 给出成本优化建议

# 输出格式

## 成本分析报告（Markdown 格式）
直接输出以下格式的成本分析报告，**不要输出 JSON，不要向用户提问**：

### 📊 成本总览
| 方案 | 显性成本 | 隐性成本 | 综合成本评级 |
|------|----------|----------|--------------|
| 选项A | ¥XXX / X小时 | 中 | ⭐⭐⭐ |
| 选项B | ¥XXX / X小时 | 高 | ⭐⭐ |

### 💰 显性成本详细分析
**选项A**
- 金钱成本：具体金额及构成
- 时间成本：所需时间及机会价值
- 资源成本：人力、物力、技术等资源投入

**选项B**
- （同上结构）

### 🎭 隐性成本评估
**机会成本**：选择某方案而放弃的其他可能性
**学习/适应成本**：掌握新技能、适应新流程所需投入
**心理成本**：决策压力、焦虑程度、情感投入
**维护/后续成本**：长期维持所需的持续投入

### ⏱️ 成本时间分布
| 阶段 | 选项A成本 | 选项B成本 |
|------|-----------|-----------|
| 前期投入 | ... | ... |
| 中期维持 | ... | ... |
| 后期回收 | ... | ... |

### 📈 风险成本评估
识别各方案的潜在风险及对应的成本影响

### 💡 成本优化建议
针对各方案的成本构成提出优化路径

### 🎯 成本决策建议
基于你的选择（[引用用户的具体回答]），推荐：XX方案，理由：XXX

---

# 约束
- **直接输出报告**：不要向用户提问，不要输出 JSON，直接输出 Markdown 格式的成本分析报告
- 客观性：基于事实和数据进行分析，避免主观臆断
- 完整性：确保覆盖所有关键成本维度，不遗漏重要隐性成本
- 可追溯性：清晰标注成本数据的来源和计算依据
- 警示性：当发现异常高成本或潜在成本陷阱时，明确警示用户
- 避免过度分析：当成本差异不明显（<10%）时，主动提示用户可考虑其他维度

# 错误处理
- 当缺少必要成本数据时，主动询问用户补充
- 当成本数据不一致或存在矛盾时，指出问题并要求澄清
- 当存在无法量化的关键成本因素时，使用定性描述并标注不确定性"""

@tool
def retrieve_cost_knowledge(decision_context: str) -> str:
    """
    从知识库检索与当前决策场景相关的成本评估专业知识。
    使用 BM25 + 向量混合检索（RRF 融合），再经 Self-RAG 过滤和 Cohere 精排，
    确保返回最高质量的成本知识片段。

    Args:
        decision_context: 决策场景描述（如"买房还是租房"、"职业选择"等）

    Returns:
        相关成本知识片段（精排后），用于指导成本分析
    """
    if not RAG_ENABLED:
        return "（知识库未启用，请安装 chromadb sentence-transformers rank-bm25）"

    try:
        # Step 1: 混合检索（BM25 + 向量 + RRF）
        docs = hybrid_retrieve("knowledge_cost", decision_context, top_k=4)

        # Step 2: Self-RAG 相关性过滤（本地模式无 API 调用，默认快速）
        docs = self_rag_filter(decision_context, docs, rel_threshold=0.4, max_docs=3, lightweight=True)

        # Step 3: Cohere 精排（或本地降级精排）
        result = format_reranked_results(decision_context, docs, top_k=2)

        # Step 4: 注册到全局 CitationManager（用于最终 References 溯源）
        if CITATION_ENABLED and _citation_mgr is not None:
            _citation_mgr.add_documents(docs, source_type="knowledge_base")

        return f"【成本知识库检索结果（混合检索+精排）】\n{result}"
    except Exception as e:
        # 降级：直接用原始检索
        chunks = retrieve_knowledge(decision_context, kb_type="cost", n_results=3)
        return format_knowledge_for_prompt(chunks, kb_type="cost")


@tool
def web_search_cost(query: str) -> str:
    """
    搜索互联网获取与成本分析相关的实时信息。
    适用于需要最新数据的场景：当前房价、贷款利率、物价水平、行业薪资等。

    Args:
        query: 搜索关键词（如"2025年北京平均房价"、"当前LPR利率"等）

    Returns:
        搜索结果摘要
    """
    if not WEB_SEARCH_ENABLED:
        return "（Web Search 未启用，请安装 duckduckgo-search）"
    try:
        _results = _run_ddg_search(query, max_results=5)
        # 提取 2 字以上关键词用于相关性校验
        import re as _re_cost
        _qkws = [w for w in _re_cost.sub(r'[^\w]+', ' ', query).split() if len(w) >= 2]
        _SPAM_WORDS_C = {'黑料', '大瓜', '吃瓜', '爆料', '爆点', '八卦', '撕逼', '扒皮', '料包', '瓜圈'}
        def _relevant_cost(r: dict) -> bool:
            title = r.get("title", "") or ""
            body = r.get("body", "") or ""
            _cn_t = sum(1 for c in title if '\u4e00' <= c <= '\u9fff') / max(len(title), 1)
            # URL 标题 / 垃圾标题过滤
            if ('/' in title and '.' in title and _cn_t < 0.05) or title.startswith(('http://', 'https://')):
                return False
            if any(w in title for w in _SPAM_WORDS_C):
                return False
            combined = title + body
            # 至少 min(2, n) 个关键词命中
            if _qkws:
                matched = sum(1 for k in _qkws if k in combined)
                if matched < min(2, len(_qkws)):
                    return False
            cn_ok = sum(1 for c in body if '\u4e00' <= c <= '\u9fff') / max(len(body), 1) >= 0.20
            return cn_ok
        _valid = [r for r in _results if _relevant_cost(r)]
        if not _valid:
            _valid = [r for r in _results if sum(1 for c in r.get("body","") if '\u4e00'<=c<='\u9fff') / max(len(r.get("body","")),1) >= 0.20]
        result_text = " ".join(r.get("body", "") for r in _valid[:3])[:800] if _valid else ""
        if CITATION_ENABLED and _citation_mgr is not None and _valid:
            from langchain_core.documents import Document as _Doc
            for _r in _valid[:2]:
                _t = (_r.get("title") or "网络实时搜索")[:60]
                _citation_mgr.add_document(
                    _Doc(page_content=_r.get("body", "")[:300], metadata={"source": _t}),
                    source_type="web_search"
                )
        return f"🌐 网络搜索结果（{query}）：\n{result_text}"
    except Exception as e:
        return f"搜索失败：{str(e)}"


cost_analysis_agent = create_react_agent(
    name="cost_analysis_agent",
    model=llm,
    tools=[retrieve_cost_knowledge, web_search_cost],
    prompt=ChatPromptTemplate.from_messages([
        ("system", COST_ANALYSIS_SYSTEM_PROMPT + "\n\n"
         "## 工具使用说明\n"
         "1. 先调用 retrieve_cost_knowledge 检索成本评估专业知识作为分析框架\n"
         "2. 当需要实时数据时（房价/利率/薪资/物价），调用 web_search_cost 搜索最新信息\n"
         "3. 综合知识库规则和实时数据，输出专业、有据可查的成本分析报告"),
        ("placeholder", "{messages}")
    ])
)

# ============================================================================
# 风险评估 Agent - 评估风险高低（不确定性、失败后果）
# ============================================================================

@tool
def retrieve_risk_knowledge(decision_context: str) -> str:
    """
    从知识库检索与当前决策场景相关的风险评估专业知识。
    使用 BM25 + 向量混合检索（RRF 融合），再经 Self-RAG 过滤和 Cohere 精排。

    Args:
        decision_context: 决策场景描述（如"换工作"、"投资股票"等）

    Returns:
        相关风险知识片段（精排后），用于指导风险评估
    """
    if not RAG_ENABLED:
        return "（知识库未启用，请安装 chromadb sentence-transformers rank-bm25）"

    try:
        # Step 1: 混合检索
        docs = hybrid_retrieve("knowledge_risk", decision_context, top_k=4)

        # Step 2: Self-RAG 过滤（本地模式无 API 调用）
        docs = self_rag_filter(decision_context, docs, rel_threshold=0.4, max_docs=3, lightweight=True)

        # Step 3: 精排
        result = format_reranked_results(decision_context, docs, top_k=2)

        # Step 4: 注册到全局 CitationManager
        if CITATION_ENABLED and _citation_mgr is not None:
            _citation_mgr.add_documents(docs, source_type="knowledge_base")

        return f"【风险知识库检索结果（混合检索+精排）】\n{result}"
    except Exception as e:
        chunks = retrieve_knowledge(decision_context, kb_type="risk", n_results=3)
        return format_knowledge_for_prompt(chunks, kb_type="risk")


@tool
def web_search_risk(query: str) -> str:
    """
    搜索互联网获取与风险评估相关的实时信息。
    适用于需要最新动态的场景：行业政策变化、公司近况、市场风险预警、安全事件等。
    
    Args:
        query: 搜索关键词（如"2025年AI行业裁员情况"、"某公司最新新闻"等）
    
    Returns:
        搜索结果摘要
    """
    if not WEB_SEARCH_ENABLED:
        return "（Web Search 未启用，请安装 duckduckgo-search）"
    try:
        _results = _run_ddg_search(query, max_results=5)
        # 提取 2 字以上关键词用于相关性校验
        import re as _re_risk
        _qkws = [w for w in _re_risk.sub(r'[^\w]+', ' ', query).split() if len(w) >= 2]
        _SPAM_WORDS_R = {'黑料', '大瓜', '吃瓜', '爆料', '爆点', '八卦', '撕逼', '扒皮', '料包', '瓜圈'}
        def _relevant_risk(r: dict) -> bool:
            title = r.get("title", "") or ""
            body = r.get("body", "") or ""
            _cn_t = sum(1 for c in title if '\u4e00' <= c <= '\u9fff') / max(len(title), 1)
            # URL 标题 / 垃圾标题过滤
            if ('/' in title and '.' in title and _cn_t < 0.05) or title.startswith(('http://', 'https://')):
                return False
            if any(w in title for w in _SPAM_WORDS_R):
                return False
            combined = title + body
            # 至少 min(2, n) 个关键词命中
            if _qkws:
                matched = sum(1 for k in _qkws if k in combined)
                if matched < min(2, len(_qkws)):
                    return False
            cn_ok = sum(1 for c in body if '\u4e00' <= c <= '\u9fff') / max(len(body), 1) >= 0.20
            return cn_ok
        _valid = [r for r in _results if _relevant_risk(r)]
        if not _valid:
            _valid = [r for r in _results if sum(1 for c in r.get("body","") if '\u4e00'<=c<='\u9fff') / max(len(r.get("body","")),1) >= 0.20]
        result_text = " ".join(r.get("body", "") for r in _valid[:3])[:800] if _valid else ""
        if CITATION_ENABLED and _citation_mgr is not None and _valid:
            from langchain_core.documents import Document as _Doc
            for _r in _valid[:2]:
                _t = (_r.get("title") or "网络实时搜索")[:60]
                _citation_mgr.add_document(
                    _Doc(page_content=_r.get("body", "")[:300], metadata={"source": _t}),
                    source_type="web_search"
                )
        return f"🌐 网络搜索结果（{query}）：\n{result_text}"
    except Exception as e:
        return f"搜索失败：{str(e)}"


risk_assessment_agent = create_react_agent(
    name="risk_assessment_agent",
    model=llm,
    tools=[retrieve_risk_knowledge, web_search_risk],
    prompt=ChatPromptTemplate.from_messages([
        ("system", (
            "你是风险评估 Agent，专注于评估决策的风险因素。\n\n"
            "工具使用说明：\n"
            "1. 先调用 retrieve_risk_knowledge 检索风险评估专业知识（分类体系、等级标准）\n"
            "2. 当需要实时信息时（行业动态/政策变化/公司近况），调用 web_search_risk 搜索\n\n"
            "评估维度：\n"
            "- 风险分类：财务/时间/关系/健康/机会风险\n"
            "- 可逆性：不可逆×1.5，部分可逆×1.2\n"
            "- 风险等级：五级体系（极低/低/中/高/极高）\n"
            "- 风险评分：概率(1-5) × 影响(1-5)\n\n"
            "输出格式：\n"
            "- 主要风险列表（每项含等级和评分）\n"
            "- 综合风险等级\n"
            "- 关键风险警示（如有）\n"
            "- 风险应对建议（规避/降低/转移/接受）"
        )),
        ("placeholder", "{messages}")
    ])
)

# ============================================================================
# 用户价值 Agent - 对照用户历史偏好
# ============================================================================

@tool
def retrieve_value_knowledge(decision_context: str) -> str:
    """
    从知识库检索与当前决策场景相关的用户价值评估专业知识。
    使用 BM25 + 向量混合检索（RRF 融合），再经 Self-RAG 过滤和 Cohere 精排。

    Args:
        decision_context: 决策场景描述

    Returns:
        相关价值评估知识片段（精排后）
    """
    if not RAG_ENABLED:
        return "（知识库未启用，请安装 chromadb sentence-transformers rank-bm25）"

    try:
        # Step 1: 混合检索
        docs = hybrid_retrieve("knowledge_value", decision_context, top_k=4)

        # Step 2: Self-RAG 过滤（本地模式无 API 调用）
        docs = self_rag_filter(decision_context, docs, rel_threshold=0.4, max_docs=3, lightweight=True)

        # Step 3: 精排
        result = format_reranked_results(decision_context, docs, top_k=2)

        # Step 4: 注册到全局 CitationManager
        if CITATION_ENABLED and _citation_mgr is not None:
            _citation_mgr.add_documents(docs, source_type="knowledge_base")

        return f"【价值知识库检索结果（混合检索+精排）】\n{result}"
    except Exception as e:
        chunks = retrieve_knowledge(decision_context, kb_type="value", n_results=3)
        return format_knowledge_for_prompt(chunks, kb_type="value")


@tool
def analyze_user_value(decision_context: str, user_id: str = "default") -> str:
    """
    分析决策是否符合用户历史偏好。
    通过 RAG 检索用户过去的相似决策，识别其偏好规律和价值取向。
    
    Args:
        decision_context: 决策问题的上下文描述
        user_id:          用户标识（默认 "default"）
    
    Returns:
        基于历史偏好的用户价值分析结果
    """
    if not RAG_ENABLED:
        return (
            f"用户价值分析：基于 '{decision_context}' 的分析。\n"
            "（RAG 模块未启用，无法检索历史偏好，请安装 chromadb 和 sentence-transformers）"
        )

    # 从向量库检索相似历史决策
    similar = retrieve_similar_decisions(
        query=decision_context,
        n_results=3,
        user_id=user_id,
    )
    history_text = format_history_for_prompt(similar)

    # 将历史决策记录注册到全局 CitationManager（memory 类型）
    if CITATION_ENABLED and _citation_mgr is not None and similar:
        from langchain_core.documents import Document as _Doc
        for _rec in similar:
            _mem_doc = _Doc(
                page_content=f"{_rec.get('scenario', '')}→{_rec.get('decision', '')}",
                metadata={
                    "_collection": "decision_history",
                    "source": f"历史记录（{_rec.get('time', '')}）",
                    "_self_rag_score": _rec.get("similarity", 0.0),
                },
            )
            _citation_mgr.add_document(_mem_doc, source_type="memory")

    if not similar:
        return (
            f"用户价值分析：这是用户首次面对此类决策场景，暂无历史偏好数据可供参考。\n"
            f"建议综合成本和风险分析结果，为用户提供基础决策建议。\n"
            f"本次决策完成后，将自动记录用户偏好供未来参考。"
        )

    return (
        f"用户价值分析（RAG 检索结果）：\n\n"
        f"{history_text}\n\n"
        f"【偏好分析】根据以上 {len(similar)} 条历史决策记录：\n"
        f"- 请分析用户在相似场景下的决策模式（倾向保守还是激进？）\n"
        f"- 识别用户重视的核心价值维度（成本优先？风险规避？体验优先？）\n"
        f"- 判断本次候选方案与用户历史偏好的匹配程度\n"
        f"- 若与历史偏好存在明显差异，需特别提示用户注意"
    )

# ── 价值评估 Agent（专注决策内在价值，使用知识库 RAG）────────────────────────
user_value_agent = create_react_agent(
    name="user_value_agent",
    model=llm,
    tools=[retrieve_value_knowledge],
    prompt=ChatPromptTemplate.from_messages([
        ("system", (
            "你是价值评估 Agent，专注于从内在价值角度评估决策方案。\n\n"
            "工具使用说明：\n"
            "调用 retrieve_value_knowledge 检索价值评估专业知识（价值框架、场景规则）。\n\n"
            "评估四个价值维度（0-10分）：\n"
            "- 功能价值：实际效用和问题解决能力\n"
            "- 情感价值：对情绪和心理健康的影响\n"
            "- 社会价值：对社会关系、地位的影响\n"
            "- 成长价值：长期发展潜力和能力提升\n\n"
            "输出格式：\n"
            "- 各方案四维度评分表\n"
            "- 加权综合价值得分（建议权重：功能30% 情感20% 社会20% 成长30%）\n"
            "- 价值优势方案（一句话结论）"
        )),
        ("placeholder", "{messages}")
    ])
)

# ── 个人匹配度 Agent（专注用户历史偏好对比，使用记忆 RAG）────────────────────
personal_match_agent = create_react_agent(
    name="personal_match_agent",
    model=llm,
    tools=[analyze_user_value],
    prompt=ChatPromptTemplate.from_messages([
        ("system", (
            "你是个人匹配度 Agent，专注于将候选方案与用户历史决策偏好进行比对，"
            "评估方案与用户个人画像的契合程度。\n\n"
            "工具使用说明：\n"
            "调用 analyze_user_value 从记忆库检索用户历史决策，获取偏好规律和画像数据。\n\n"
            "分析流程：\n"
            "1. 获取历史偏好数据，识别用户偏好类型：\n"
            "   - 保守型（风险规避，倾向稳定）\n"
            "   - 激进型（高风险高收益导向）\n"
            "   - 成本敏感型（优先最小化成本）\n"
            "   - 成长导向型（优先长期发展）\n"
            "   - 体验优先型（注重过程感受）\n"
            "2. 对比每个候选方案与用户偏好画像的匹配度（0-100%）\n"
            "3. 若某方案与历史偏好存在明显冲突，标注风险提示\n"
            "4. 若无历史记录，说明首次决策，无法进行偏好匹配\n\n"
            "输出格式：\n"
            "- 用户偏好类型（有历史数据时）及置信度\n"
            "- 各方案偏好匹配度评分（百分比）\n"
            "- 偏好冲突警告（如有）\n"
            "- 个人匹配度结论（一句话）"
        )),
        ("placeholder", "{messages}")
    ])
)

# ============================================================================
# 综合 Agent（Supervisor）- 最终聚合判断
# ============================================================================

# 创建手部转移工具（综合 Agent 可以调用三个分析 Agent）
transfer_to_cost_analysis = create_handoff_tool(
    agent_name="cost_analysis_agent",
    description="转交给成本分析 Agent 进行成本评估",
)

transfer_to_risk_assessment = create_handoff_tool(
    agent_name="risk_assessment_agent",
    description="转交给风险评估 Agent 进行风险评估",
)

transfer_to_user_value = create_handoff_tool(
    agent_name="user_value_agent",
    description="转交给价值评估 Agent，评估方案的功能/情感/社会/成长四维度内在价值",
)

transfer_to_personal_match = create_handoff_tool(
    agent_name="personal_match_agent",
    description="转交给个人匹配度 Agent，对比用户历史决策偏好，评估方案与个人画像的契合程度（记忆 RAG）",
)

@tool
def recognize_decision_intent(user_query: str) -> str:
    """
    【意图识别】对用户决策问题进行意图分类和问题重写。
    将模糊表述转化为结构化意图标签，提取关键决策要素，
    并将问题重写为更清晰的形式，帮助后续 Agent 精准分析。

    Args:
        user_query: 用户原始决策问题

    Returns:
        意图识别结果（含意图标签、重写后问题、关键要素）
    """
    if not INTENT_ENABLED:
        return f"意图识别模块未加载。原始问题：{user_query}"

    try:
        intent = recognize_intent(user_query)
        return format_intent_for_prompt(intent)
    except Exception as e:
        return f"意图识别失败（{e}），使用原始问题继续分析。"


@tool
def finalize_decision(
    user_query: str,
    cost_analysis: str,
    risk_assessment: str,
    user_value: str,
    personal_match: str,
    final_recommendation: str,
    user_id: str = "default",
) -> str:
    """
    综合 Agent 的工具：汇总四个专家 Agent 的分析结果，输出最终判断，
    自动保存到历史记录（RAG 记忆），并附加 Citation 决策依据溯源。

    Args:
        user_query:           用户原始决策问题
        cost_analysis:        成本分析结果摘要（来自 cost_analysis_agent）
        risk_assessment:      风险评估结果摘要（来自 risk_assessment_agent）
        user_value:           价值评估结果摘要（来自 user_value_agent）
        personal_match:       个人匹配度分析摘要（来自 personal_match_agent，含偏好画像对比）
        final_recommendation: 最终决策推荐（例如："推荐选择方案A，原因是..."）
        user_id:              用户标识

    Returns:
        最终决策判断报告（含 Citation 来源）
    """
    result = (
        f"## 【DecideX 综合决策报告】\n\n"
        f"### 💰 成本分析\n{cost_analysis}\n\n"
        f"### ⚠️ 风险评估\n{risk_assessment}\n\n"
        f"### 🎯 价值评估\n{user_value}\n\n"
        f"### 👤 个人匹配度\n{personal_match}\n\n"
        f"### ✅ 最终决策建议\n{final_recommendation}"
    )

    # Citation：用 CitationManager 生成真正的 References 列表
    if CITATION_ENABLED and _citation_mgr is not None and _citation_mgr.has_sources:
        # 基于本轮所有检索文档生成带编号的参考文献
        cited = _citation_mgr.build_cited_decision(
            answer=final_recommendation,
            intent_label="general",
            include_all=True,   # 展示所有检索到的来源
        )
        # 生成 References 段落（📚知识库 / 🧠历史记忆 / 🌐网络搜索 分类显示）
        if cited.references:
            ref_lines = ["\n\n---\n📎 **决策依据来源**\n"]
            kb_refs   = [r for r in cited.references if r.source_type == "knowledge_base"]
            mem_refs  = [r for r in cited.references if r.source_type == "memory"]
            web_refs  = [r for r in cited.references if r.source_type == "web_search"]

            if kb_refs:
                ref_lines.append("📚 **知识库**")
                ref_lines.extend(r.to_reference_str() for r in kb_refs)
            if mem_refs:
                ref_lines.append("\n🧠 **历史决策记忆**")
                ref_lines.extend(r.to_reference_str() for r in mem_refs)
            if web_refs:
                ref_lines.append("\n🌐 **网络搜索**")
                ref_lines.extend(r.to_reference_str() for r in web_refs)

            result += "\n".join(ref_lines)

        # 清空，为下次决策做准备
        _citation_mgr.clear()
    elif CITATION_ENABLED:
        # 无检索来源时给出通用说明
        result += (
            "\n\n---\n📎 **决策依据说明**\n"
            "本报告基于 LLM 推理生成，本次未检索到专业知识库或历史记录数据。"
        )

    # 自动保存本次决策到向量库（RAG 记忆）
    if RAG_ENABLED:
        try:
            doc_id = save_decision(
                user_query=user_query,
                decision_result=final_recommendation,
                cost_summary=cost_analysis[:300],
                risk_summary=risk_assessment[:300],
                value_summary=f"{user_value[:150]} | 匹配度：{personal_match[:150]}",
                user_id=user_id,
            )
            result += f"\n\n📝 *本次决策已记录（ID: {doc_id[:20]}...），将用于未来个性化分析。*"
        except Exception as e:
            result += f"\n\n⚠️ *决策记录保存失败：{str(e)}*"

    return result

@tool
def evaluate_stop(
    top_recommendation: str,
    confidence_scores: str,
    key_points: str,
    controversy_count: int = 0,
) -> str:
    """
    【停止规则评估】判断当前分析是否应该停止，防止无效循环。
    综合 Agent 在每轮分析完成后必须调用此工具。

    实现三类停止规则：
    - B（收敛停止）：连续两轮 Top1 推荐不变且领先优势 ≥ 0.12
    - C（低收益停止）：本轮新增观点 < 2 个，或观点重复率 ≥ 70%
    - A（硬停止）：分析轮次 ≥ 3 轮必须结束
    
    Args:
        top_recommendation: 当前轮 Top1 推荐方案名（如"方案A"或"选择跳槽"）
        confidence_scores:  各方案置信度，JSON字符串，如 '{"方案A": 0.85, "方案B": 0.60}'
        key_points:         本轮关键观点，逗号分隔，如 "成本差异显著,风险可控,符合用户偏好"
        controversy_count:  当前争议点数量（整数）
    
    Returns:
        停止评估结果（JSON字符串），含 should_stop、reason、stop_type、round_num
    """
    import json
    try:
        scores = json.loads(confidence_scores) if isinstance(confidence_scores, str) else confidence_scores
    except Exception:
        scores = {}

    points = [p.strip() for p in key_points.split(",") if p.strip()] if key_points else []

    result = check_should_stop(
        top_recommendation=top_recommendation,
        confidence_scores=scores,
        key_points=points,
        controversy_count=controversy_count,
    )

    if result["should_stop"]:
        return (
            f"🛑 **停止信号（{result['stop_type']}）**\n"
            f"轮次：{result['round_num']}\n"
            f"原因：{result['reason']}\n"
            f"→ 请立即调用 finalize_decision 输出最终结论，不要再调用子 Agent。"
        )
    else:
        return (
            f"✅ 继续分析（第 {result['round_num']} 轮）\n"
            f"结论尚未收敛，可继续调用子 Agent 补充分析。\n"
            f"注意：最多还可分析 {MAX_ROUNDS - result['round_num']} 轮。"
        )


# ============================================================================
# 性能优化工具：RAG + Web Search + 多角色分析 合并为单一工具
# comprehensive_agent 只需调用 1 个工具，彻底消除 LLM 多步乱序问题
# LLM 调用从 ~30 次降至 2 次（意图识别 + 多角色分析）
# ============================================================================

@tool
def full_decision_analysis(decision_query: str, user_profile: str = "", mode: str = "detailed") -> str:
    """
    【一站式决策分析】在单次调用内完成全部分析流程：
    1. BM25+向量混合检索（RRF融合）+ Self-RAG过滤 + Cohere精排 ← 知识库RAG
    2. DuckDuckGo实时网络搜索 ← 获取最新价格/政策/行业数据
    3. Multi-Agent多角色单次LLM推理 ← 成本/风险/价值/个人匹配度四维分析
    4. 生成【DecideX 综合决策报告】

    等价于依次调用 cost_analysis_agent、risk_assessment_agent、
    user_value_agent、personal_match_agent，但只消耗一次 LLM API 调用。

    Args:
        decision_query: 用户决策问题（完整原始问题）
        user_profile:   用户画像JSON字符串（城市/预算/风险偏好等）
        mode:           输出模式，"detailed"（完整报告）或 "simple"（精简结论，200字以内）

    Returns:
        含成本/风险/价值/个人匹配度的完整决策报告（Markdown格式）
    """
    from langchain_core.messages import HumanMessage as _HM, SystemMessage as _SM
    from datetime import datetime as _dt
    current_year = _dt.now().year

    # ── Step 1: RAG 知识库检索（BM25+向量+RRF+Self-RAG+Cohere精排）────────────
    rag_sections = []
    if RAG_ENABLED:
        for kb_type, label in [("knowledge_cost", "成本"), ("knowledge_risk", "风险"), ("knowledge_value", "价值")]:
            try:
                docs = hybrid_retrieve(kb_type, decision_query, top_k=3)
                docs = self_rag_filter(decision_query, docs, rel_threshold=0.3, max_docs=2, lightweight=True)
                result = format_reranked_results(decision_query, docs, top_k=2)
                if CITATION_ENABLED and _citation_mgr is not None:
                    _citation_mgr.add_documents(docs, source_type="knowledge_base")
                rag_sections.append(f"**{label}知识库**：\n{result}")
            except Exception:
                try:
                    kb_key = kb_type.replace("knowledge_", "")
                    chunks = retrieve_knowledge(decision_query, kb_type=kb_key, n_results=2)
                    rag_sections.append(f"**{label}知识库**：\n{format_knowledge_for_prompt(chunks, kb_type=kb_key)}")
                except Exception:
                    pass
    rag_context = "\n\n".join(rag_sections)

    # ── Step 2: Web Search（带年份的实时数据搜索）─────────────────────────────
    web_context = ""
    if WEB_SEARCH_ENABLED:
        # 提取关键词：去掉标点，取前 5 个词组，拼接年份
        import re as _re
        _kw = _re.sub(r'[？?！!。，,、；;：:「」【】《》()（）\s]+', ' ', decision_query).strip()
        _kw = ' '.join(_kw.split()[:5])
        web_search_query = f"{_kw} {current_year}年"
        def _cn_ratio(text: str) -> float:
            """中文字符占比（用于过滤英文/乱码垃圾结果）"""
            return sum(1 for c in text if '\u4e00' <= c <= '\u9fff') / max(len(text), 1)

        # 垃圾/八卦/低质内容标题关键词
        _SPAM_TITLE_WORDS = {'黑料', '大瓜', '吃瓜', '爆料', '爆点', '八卦', '撕逼',
                             '每日热搜', '热门大赛', '扒皮', '料包', '瓜圈', '劲爆'}

        def _title_is_url(title: str) -> bool:
            """判断标题是否像 URL 路径（如 wiki.xxx.cc/archives/204725.html）"""
            if not title:
                return True
            has_slash = '/' in title
            has_dot = '.' in title
            no_chinese = _cn_ratio(title) < 0.05
            looks_like_url = has_slash and has_dot and no_chinese
            is_http = title.strip().startswith(('http://', 'https://'))
            return looks_like_url or is_http

        def _is_quality(r: dict) -> bool:
            """只过滤明显垃圾：URL标题、八卦词、非中文内容。
            DDG 本身已按相关性排序，不再做额外关键词匹配，避免过度过滤导致 citation 消失。"""
            title = r.get("title", "") or ""
            body  = r.get("body",  "") or ""
            if _title_is_url(title):
                return False
            if any(w in title for w in _SPAM_TITLE_WORDS):
                return False
            # 正文需有一定中文内容（≥15%）
            return _cn_ratio(body) >= 0.15 if body else False

        try:
            _raw_results = _run_ddg_search(web_search_query, max_results=5)
            _valid = [r for r in _raw_results if _is_quality(r)]
            if _valid:
                # 拼接正文供 LLM 阅读
                web_context = " ".join(r.get("body", "") for r in _valid[:3])[:1000]
                # Citation：只取前 2 条有效结果，用文章标题作来源名
                if CITATION_ENABLED and _citation_mgr is not None:
                    from langchain_core.documents import Document as _Doc
                    for _r in _valid[:2]:
                        _title = (_r.get("title") or "网络实时搜索")[:60]
                        _snippet = _r.get("body", "")[:300]
                        _citation_mgr.add_document(
                            _Doc(page_content=_snippet,
                                 metadata={"source": _title}),
                            source_type="web_search"
                        )
        except Exception as e:
            web_context = f"（搜索失败：{e}）"

    # ── Step 3: Multi-Agent 多角色单次 LLM 推理（Chain-of-Thought）───────────
    # 四个专家角色描述（两种模式共用）
    _role_definitions = (
        f"你是 DecideX 多 Agent 决策系统的核心推理引擎（当前年份：{current_year}年）。\n"
        f"所有数据、政策、价格、利率等信息必须基于 {current_year} 年最新情况。\n"
        f"如果你不确定 {current_year} 年的具体数据，请基于实时数据部分，或明确注明数据来源年份。\n\n"
        "你同时扮演四个专家角色，对决策进行多维度分析：\n\n"
        "### 💰 成本分析专家（Cost Agent）\n"
        "分析显性成本（金钱、时间）和隐性成本（机会成本、心理成本、维护成本）。\n"
        "给出各方案成本等级（低/中/高）和关键成本驱动因素。\n\n"
        "### ⚠️ 风险评估专家（Risk Agent）\n"
        "识别财务风险、时间风险、机会风险、可逆性。\n"
        "每项风险给出：概率（1-5）× 影响（1-5）= 风险评分，并给出综合风险等级。\n\n"
        "### 🎯 价值评估专家（Value Agent）\n"
        "评估功能价值、情感价值、社会价值、成长价值（各0-10分）。\n"
        "加权综合得分（功能30% 情感20% 社会20% 成长30%）。\n"
        "⚠️ 禁止使用 Markdown 表格，改用 bullet 列表格式。\n\n"
        "### 👤 个人匹配度专家（PersonalMatch Agent）\n"
        "基于用户画像（风险偏好、预算、目标等），评估方案与用户风格匹配程度（百分比）。\n"
        "从以下类型中选 1-2 个：保守型、平衡型、激进型、成本敏感型、成长导向型、体验优先型。\n"
        "严格以用户画像中实际记录的风险偏好为准，不要自行推断。\n\n"
        "⚠️ 禁止输出JSON、禁止代码块（```）、禁止 Markdown 表格、禁止任何序列化格式。\n"
        "⚠️ 禁止在报告中向用户提问或追问任何信息（如：请问您的预算是多少），直接基于已有信息输出报告。\n"
        "全程中文。\n\n"
    )

    # 无论 mode 如何，内部始终生成完整详细报告（压缩由 backend_proxy 的 _compress_to_simple 处理）
    if True:
        system_prompt = (
            _role_definitions +
            "## 输出格式（详细模式）\n"
            "请对每个专家角色**充分展开分析**，输出完整决策报告（总字数不少于800字）：\n\n"
            "# 【DecideX 综合决策报告】\n\n"
            "## 💰 成本分析\n"
            "（详细分析，含具体数字，覆盖初始成本、月度支出、机会成本，至少200字）\n\n"
            "## ⚠️ 风险评估\n"
            "（各类风险逐项评分，给出概率×影响=评分，综合风险等级，至少200字）\n\n"
            "## 🎯 价值评估\n"
            "（四维度 bullet 评分，每项一行含说明，最后一行输出加权综合得分，至少150字）\n\n"
            "## 👤 个人匹配度\n"
            "（基于用户画像详细说明，末尾给出偏好类型和匹配百分比，至少200字）\n\n"
            "## ✅ 综合推荐\n"
            "（明确行动建议，给出优先推荐方案及理由，至少150字）"
        )

    context_parts = []
    if user_profile:
        context_parts.append(f"【用户画像】\n{user_profile}")
    if rag_context:
        context_parts.append(f"【知识库参考】\n{rag_context[:2000]}")
    if web_context:
        context_parts.append(f"【{current_year}年实时数据】\n{web_context[:1000]}")

    user_msg = f"决策问题：{decision_query}"
    if context_parts:
        user_msg += "\n\n" + "\n\n".join(context_parts)

    try:
        resp = llm.invoke([_SM(content=system_prompt), _HM(content=user_msg)])
        content = resp.content
        if isinstance(content, list):
            content = " ".join(
                item.get("text", "") if isinstance(item, dict) else str(item)
                for item in content
            )
        result = str(content)

        # ── Citation：将本轮 RAG + Web Search 来源追加到报告末尾 ────────────
        if CITATION_ENABLED and _citation_mgr is not None and _citation_mgr.has_sources:
            cited = _citation_mgr.build_cited_decision(
                answer=result,
                intent_label="general",
                include_all=True,
            )
            if cited.references:
                ref_lines = ["\n\n---\n📎 **决策依据来源**\n"]
                kb_refs  = [r for r in cited.references if r.source_type == "knowledge_base"]
                mem_refs = [r for r in cited.references if r.source_type == "memory"]
                web_refs = [r for r in cited.references if r.source_type == "web_search"]
                if kb_refs:
                    ref_lines.append("📚 **知识库**")
                    ref_lines.extend(r.to_reference_str() for r in kb_refs)
                if mem_refs:
                    ref_lines.append("\n🧠 **历史决策记忆**")
                    ref_lines.extend(r.to_reference_str() for r in mem_refs)
                if web_refs:
                    ref_lines.append("\n🌐 **网络搜索**")
                    ref_lines.extend(r.to_reference_str() for r in web_refs)
                result += "\n".join(ref_lines)
            _citation_mgr.clear()

        return result
    except Exception as e:
        return f"分析失败：{str(e)}"


comprehensive_agent = create_react_agent(
    name="comprehensive_agent",
    model=llm,
    tools=[full_decision_analysis],
    prompt=ChatPromptTemplate.from_messages([
        ("system", (
            "你是综合决策 Agent。\n\n"
            "## 唯一任务\n"
            "调用 full_decision_analysis 工具一次，传入：\n"
            "- decision_query: 从消息中提取用户的决策问题\n"
            "- user_profile: 从消息【用户画像】部分提取的 JSON 字符串（没有则传空字符串）\n\n"
            "## 严格禁止\n"
            "- 禁止生成任何文字回复（包括'我已完成分析'、'报告如下'等描述性文字）\n"
            "- 禁止重复调用工具\n"
            "- 工具结果返回后立即停止，不做任何补充说明"
        )),
        ("placeholder", "{messages}")
    ])
)

# ============================================================================
# 创建 Supervisor Graph
# ============================================================================

supervisor_prompt = (
    "你是顶层路由 Supervisor，只负责把消息路由给 comprehensive_agent。\n\n"
    "## 唯一规则\n"
    "无论收到任何消息（包括来自子 Agent 的返回消息），只做一件事：\n"
    "→ 调用 transfer_to_comprehensive_agent\n\n"
    "## 严格禁止\n"
    "你没有以下工具，禁止尝试调用：\n"
    "analyze_cost, analyze_risk, analyze_user_value, recognize_decision_intent,\n"
    "evaluate_stop, finalize_decision, retrieve_cost_knowledge, web_search_cost\n"
    "（调用这些会报错，不要尝试）\n\n"
    "## 终止条件\n"
    "当消息中出现 '【DecideX 综合决策报告】' 或 'FINISH' 时，直接输出 FINISH 结束对话。\n\n"
    f"硬性约束：超过 {MAX_ROUNDS} 轮必须强制输出 FINISH。"
)

_supervisor_builder = create_supervisor(
    agents=[
        comprehensive_agent,
        cost_analysis_agent,
        risk_assessment_agent,
        user_value_agent,
        personal_match_agent,
    ],
    model=llm,
    prompt=supervisor_prompt,
)

# 不使用 MemorySaver：避免历史消息重放导致图多次执行
# 用户画像通过 profile_ctx 注入到每次请求的 HumanMessage 中
if hasattr(_supervisor_builder, 'compile'):
    graph = _supervisor_builder.compile()
else:
    graph = _supervisor_builder
