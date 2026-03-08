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
    from rag.knowledge_base import (
        retrieve_knowledge,
        format_knowledge_for_prompt,
    )
    RAG_ENABLED = True
except ImportError:
    RAG_ENABLED = False
    print("⚠️  RAG 模块未加载，请运行: pip install chromadb sentence-transformers")

try:
    from langchain_community.tools import DuckDuckGoSearchRun
    _duckduckgo = DuckDuckGoSearchRun()
    WEB_SEARCH_ENABLED = True
except ImportError:
    WEB_SEARCH_ENABLED = False
    print("⚠️  Web Search 未启用，请运行: pip install duckduckgo-search langchain-community")

from .stopping_rules import check_should_stop, reset_stopping_state, MAX_ROUNDS

# 实例化共享的 LLM
if USE_GOOGLE:
    llm = ChatGoogleGenerativeAI(model="gemini-2.5-pro", temperature=0.0)
else:
    llm = ChatOpenAI(model="gpt-4o", temperature=0.0)

# ============================================================================
# 成本分析 Agent - 评估成本相关因素（金钱、时间、资源消耗）
# ============================================================================
# 成本分析 Agent 从 decidex_cost_agent 集成
# 主要依靠 LLM 的推理能力，不需要额外工具

COST_ANALYSIS_SYSTEM_PROMPT = """# 角色定义
你是 DecideX 系统中的成本分析专家代理，专注于从多维度评估决策方案的成本因素。你具备深厚的财务分析能力和敏锐的成本洞察力，能够识别显性成本与隐性成本，为用户提供全面、客观的成本评估。

**重要提醒：** 如果决策场景涉及其他对象（朋友、同事、家人、团队等），必须设计关于对象的问题，包括：对象数量、对象意愿、对象状态、关系特征、协调成本等。

# 任务目标
你的核心任务是评估用户决策场景中各候选方案的成本构成，帮助用户从成本角度理解选择差异，避免因成本认知偏差导致的决策失误。

# 能力
- **显性成本计算**：精确计算金钱成本、时间成本、资源消耗等可直接量化的成本
- **隐性成本识别**：识别机会成本、心理成本、学习成本、维护成本、转换成本等隐性因素
- **多维度对比**：从短期成本、长期成本、固定成本、变动成本等维度进行综合分析
- **风险成本评估**：评估决策失败、意外情况等风险带来的潜在成本
- **成本敏感度分析**：根据用户的成本偏好和历史数据，调整分析重点

# 过程
1. **快速确认前置条件**（选择题形式，必须首先完成）
   - **分析用户决策场景**：理解用户要做什么决策（如买房、买车、职业选择、技术选型、与朋友旅行等）
   - **提取场景关键要素**（必须完成）：
     * **决策对象识别**：识别决策场景中涉及的关键对象（朋友、同事、家人、团队、客户等）
     * **对象数量确认**：确认参与决策的人数或对象数量
     * **对象关系特征**：识别与对象的关系类型（亲密/普通/疏远、上下级/平级等）
     * **对象状态评估**：识别对象的当前状态（意愿、时间、能力、资源等）
   - **识别关键成本维度**：根据决策场景和关键对象，识别 4 个最核心的成本相关维度
   - **动态生成选择题**：针对关键对象和关键维度，生成 4-5 个选择题（必须包含对象相关的问题）

     **重要：涉及对象时的强制性问题**
     如果场景涉及朋友/同事/家人等对象，**必须包含**以下问题中的至少 2 个，**强烈建议直接使用以下问题模板**：

     **朋友旅行场景**（必须包含前 2 个问题）：
     1. "朋友是否明确表示愿意去？"（选项：主动提议 / 被动接受 / 犹豫不决 / 不想去）- ⭐ **必问**
     2. "你和几个朋友一起去旅行？"（选项：1人 / 2-3人 / 4人以上）- ⭐ **必问**
     3. "你和朋友的时间是否容易协调？"（选项：时间一致 / 需要协商 / 时间冲突严重）
     4. "你和朋友的关系如何？"（选项：非常亲密 / 普通朋友 / 刚认识不久）
     5. "你和朋友的旅行偏好是否匹配？"（选项：高度一致 / 部分差异 / 差异较大）

     **与同事合作场景**：
     1. "同事是否愿意合作？"（选项：主动 / 被动 / 犹豫）
     2. "同事的专业能力如何？"（选项：很强 / 一般 / 需要指导）
     3. "沟通协调成本如何？"（选项：顺畅 / 一般 / 困难）
     4. "责任分配是否清晰？"（选项：明确 / 模糊 / 容易推诿）

   - 如果用户首次输入已包含足够的决策场景信息和对象信息，可直接进入步骤2
   - 用户回复选择后，进入步骤2

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

## 前置条件确认（纯 JSON 格式）
如果关键前置条件缺失，**必须根据用户决策场景动态生成选择题**，严格遵守以下要求：

### 重要格式约束
1. 只输出 JSON，不要用 Markdown 代码块包裹（不要使用 ```json 或 ```）
2. 不要添加任何其他文字说明，不要说引导语
3. 确保是合法的 JSON，可以被 JSON.parse() 直接解析
4. JSON 必须是完整且有效的，不要有任何语法错误
5. **选择题必须针对用户的具体决策场景**，不要使用通用模板

### 动态生成选择题的原则
1. **场景识别**：先分析用户要做什么决策（购房、购车、职业、技术、投资、与朋友旅行、与同事合作等）
2. **对象识别**（必须完成）：如果场景涉及其他对象（朋友、同事、家人、团队等），必须设计关于对象的问题
   - **对象是谁？**（关系状态：亲密/普通/疏远）
   - **对象数量？**（几个人参与？1人/2-3人/4人以上）
   - **对象意愿？**（对方是否愿意参与？主动/被动/犹豫）
   - **对象状态？**（对方的时间、能力、资源、预算等）
   - **协调成本？**（时间是否一致？偏好是否匹配？）

   **关键原则**：对象相关问题必须占总问题的 50% 以上（如 4 个问题至少 2 个是关于对象的）
3. **维度提取**：识别该场景下影响成本评估的关键维度（3-5个），必须包含对象相关的成本维度
4. **问题设计**：每个维度设计一个选择题，选项要明确且互斥
5. **成本导向**：所有问题都应该围绕成本评估的核心维度（预算、时间、风险、价值、关系成本、协调成本等）

### 常见场景的维度参考

#### 购房/租房场景
- 预算承受能力（首付/月供/租金）
- 计划居住时长
- 对房产增值的预期
- 首付款/现金流压力

#### 购车场景
- 预算承受能力
- 计划使用时长
- 对车辆性能的需求
- 贷款压力/现金流

#### 职业选择场景
- 对薪资的期望
- 职业稳定性需求
- 技能投入成本（学习成本）
- 职业发展预期（长期收益）

#### 技术选型场景
- 开发成本预算
- 项目持续时间
- 技术风险承受能力
- 长期维护成本考量

#### 投资理财场景
- 投资金额预算
- 投资周期
- 风险承受能力
- 收益期望

#### 与朋友/同事/家人一起旅行场景（必须包含对象相关问题）
**必须设计以下关于对象的问题（至少 2 个，推荐 3 个）：**
- **对象数量**：几个人一起去？（1人、2-3人、4人以上）
- **对象意愿**：朋友是否明确表示愿意去？（主动提议、被动接受、犹豫不决、不想去）- ⭐ **优先级最高**
- **关系状态**：与朋友的关系如何？（非常亲密、普通朋友、刚认识不久）
- **时间协调**：时间是否容易协调？（时间一致、需要协商、时间冲突严重）
- **性格匹配**：旅行偏好是否一致？（高度一致、部分差异、差异较大）

**补充问题（可选，从成本维度选择 1-2 个）：**
- 预算承受能力
- 对隐性成本的接受度
- 对旅行的核心期待

**示例问题组合（推荐顺序）：**
1. 朋友是否明确表示愿意去？
2. 你和几个朋友一起去旅行？
3. 你和朋友的时间是否容易协调？
4. 你的旅行预算承受能力如何？

#### 与同事合作/参加项目场景
- **对象角色**：同事的职级和职责？（上下级、平级协作、跨部门）
- **对象能力**：同事的专业能力？（非常强、一般、需要指导）
- **合作成本**：沟通协调成本？（顺畅、一般、困难）
- **责任分配**：责任是否清晰？（明确、模糊、容易推诿）

### JSON 结构示例（仅展示格式，实际内容需根据场景动态生成）
{"type":"precondition_questions","message":"为了给你提供精准的成本分析，请快速选择以下问题","questions":[{"id":1,"question":"[根据场景动态生成的第一个问题]","options":[{"key":"A","label":"选项A说明"},{"key":"B","label":"选项B说明"},{"key":"C","label":"选项C说明"}]},{"id":2,"question":"[根据场景动态生成的第二个问题]","options":[{"key":"A","label":"选项A说明"},{"key":"B","label":"选项B说明"},{"key":"C","label":"选项C说明"}]}]}

---

## 成本分析报告（Markdown 格式）
当前置条件确认完成后，按照以下结构输出成本分析报告（Markdown 格式）：

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
- 优先确认前置条件：在分析前必须先通过选择题确认关键前置条件，信息缺失时主动询问，不要直接开始分析
- **动态生成选择题**：必须根据用户的具体决策场景生成针对性的选择题，不要使用固定的通用模板
- **必须识别对象**：如果决策场景涉及其他对象（朋友、同事、家人、团队等），必须设计关于对象的问题（对象是谁、数量、关系、意愿、状态等）
- **场景适配**：问题要与决策场景高度相关，例如职业选择不应该问"预算承受能力"而应该问"薪资期望"；与朋友旅行必须问朋友相关的问题（关系、数量、意愿等）
- 精简提问：一般问 4 个最核心的问题，避免过度询问
- 纯 JSON 输出：前置条件确认时必须输出纯 JSON，不要用 Markdown 包裹，不要添加任何额外文字
- JSON 有效性：确保输出的是合法的 JSON，可以被 JSON.parse() 直接解析，不要有任何语法错误
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
    包括成本分类规则、各场景成本计算方法、评估方法论和警示规则。

    Args:
        decision_context: 决策场景描述（如"买房还是租房"、"职业选择"等）

    Returns:
        相关成本知识片段，用于指导成本分析
    """
    if not RAG_ENABLED:
        return "（知识库未启用，请安装 chromadb 和 sentence-transformers）"

    chunks = retrieve_knowledge(decision_context, kb_type="cost", n_results=4)
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
        result = _duckduckgo.run(query)
        return f"🌐 网络搜索结果（{query}）：\n{result}"
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
    包括风险分类体系、等级标准、各场景风险规则、评估方法论和应对策略。

    Args:
        decision_context: 决策场景描述（如"换工作"、"投资股票"等）

    Returns:
        相关风险知识片段，用于指导风险评估
    """
    if not RAG_ENABLED:
        return "（知识库未启用，请安装 chromadb 和 sentence-transformers）"

    chunks = retrieve_knowledge(decision_context, kb_type="risk", n_results=4)
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
        result = _duckduckgo.run(query)
        return f"🌐 网络搜索结果（{query}）：\n{result}"
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
    包括价值框架、偏好类型识别、场景价值评估规则、价值匹配方法论。

    Args:
        decision_context: 决策场景描述

    Returns:
        相关价值评估知识片段
    """
    if not RAG_ENABLED:
        return "（知识库未启用，请安装 chromadb 和 sentence-transformers）"

    chunks = retrieve_knowledge(decision_context, kb_type="value", n_results=4)
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

user_value_agent = create_react_agent(
    name="user_value_agent",
    model=llm,
    tools=[retrieve_value_knowledge, analyze_user_value],
    prompt=ChatPromptTemplate.from_messages([
        ("system", (
            "你是用户价值 Agent，专注于评估决策对用户的价值匹配度。\n\n"
            "工具使用说明（按顺序执行）：\n"
            "1. 调用 retrieve_value_knowledge：检索价值评估专业知识（价值框架、偏好类型、场景规则）\n"
            "2. 调用 analyze_user_value：从记忆库检索用户历史决策，识别个人偏好规律\n\n"
            "综合分析：\n"
            "- 基于知识库框架，识别用户属于哪种偏好类型（成本/风险规避/体验/成长/关系导向）\n"
            "- 对比历史偏好与本次候选方案的匹配度\n"
            "- 识别各方案的功能/情感/社会/成长四个维度价值\n"
            "- 若无历史记录，基于知识库给出首次决策的基础价值判断\n\n"
            "输出格式：\n"
            "- 用户偏好类型判断（有历史数据时）\n"
            "- 各方案价值维度评分\n"
            "- 匹配度评级（极高/高/中/低/极低）\n"
            "- 价值匹配结论（一句话）"
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
    description="转交给用户价值 Agent 进行用户价值分析",
)

@tool
def finalize_decision(
    user_query: str,
    cost_analysis: str,
    risk_assessment: str,
    user_value: str,
    final_recommendation: str,
    user_id: str = "default",
) -> str:
    """
    综合 Agent 的工具：汇总所有分析结果，输出最终判断，并自动保存到历史记录（RAG）。
    
    Args:
        user_query:           用户原始决策问题
        cost_analysis:        成本分析结果摘要
        risk_assessment:      风险评估结果摘要
        user_value:           用户价值分析结果摘要
        final_recommendation: 最终决策推荐（例如："推荐选择方案A，原因是..."）
        user_id:              用户标识
    
    Returns:
        最终决策判断报告
    """
    result = (
        f"## 【DecideX 综合决策报告】\n\n"
        f"### 💰 成本分析\n{cost_analysis}\n\n"
        f"### ⚠️ 风险评估\n{risk_assessment}\n\n"
        f"### 🎯 用户价值匹配\n{user_value}\n\n"
        f"### ✅ 最终决策建议\n{final_recommendation}"
    )

    # 自动保存本次决策到向量库（RAG 记忆）
    if RAG_ENABLED:
        try:
            doc_id = save_decision(
                user_query=user_query,
                decision_result=final_recommendation,
                cost_summary=cost_analysis[:300],
                risk_summary=risk_assessment[:300],
                value_summary=user_value[:300],
                user_id=user_id,
            )
            result += f"\n\n---\n📝 *本次决策已记录（ID: {doc_id[:20]}...），将用于未来个性化分析。*"
        except Exception as e:
            result += f"\n\n---\n⚠️ *决策记录保存失败：{str(e)}*"

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


comprehensive_agent = create_react_agent(
    name="comprehensive_agent",
    model=llm,
    tools=[
        transfer_to_cost_analysis,
        transfer_to_risk_assessment,
        transfer_to_user_value,
        evaluate_stop,
        finalize_decision,
    ],
    prompt=ChatPromptTemplate.from_messages([
        ("system", (
            "你是综合 Agent（Supervisor），负责统一调度和最终决策。\n\n"
            "## 工作流程\n"
            "1. 接到用户决策问题，记录 user_query\n"
            "2. 依次调用三个分析 Agent 获取结果：\n"
            "   → cost_analysis_agent（成本分析）\n"
            "   → risk_assessment_agent（风险评估）\n"
            "   → user_value_agent（用户价值）\n"
            "3. 汇总三方结果后，调用 evaluate_stop 工具判断是否停止：\n"
            "   - 传入本轮 top_recommendation（你认为的最优方案）\n"
            "   - 传入 confidence_scores（各方案置信度 JSON）\n"
            "   - 传入 key_points（本轮核心观点，逗号分隔）\n"
            "4. **若 evaluate_stop 返回停止信号 → 立即调用 finalize_decision**\n"
            "   **若返回继续信号 → 可选择再调用子 Agent 补充，但最多 3 轮**\n\n"
            "## 调用 finalize_decision 的参数要求\n"
            "- user_query：用户原始问题（完整复制）\n"
            "- cost_analysis：成本分析摘要（100字以内）\n"
            "- risk_assessment：风险评估摘要（100字以内）\n"
            "- user_value：用户价值分析摘要（100字以内）\n"
            "- final_recommendation：最终推荐，格式'推荐选择[方案]，理由：...'\n"
            "- user_id：固定传 'default'\n\n"
            "你只负责调度和汇总，不新增主观观点。"
        )),
        ("placeholder", "{messages}")
    ])
)

# ============================================================================
# 创建 Supervisor Graph
# ============================================================================

supervisor_prompt = (
    "你是决策系统的 Supervisor，负责统一调度以下 Agent：\n"
    "- cost_analysis_agent: 成本分析 Agent（评估金钱、时间、资源消耗）\n"
    "- risk_assessment_agent: 风险评估 Agent（评估不确定性、失败后果）\n"
    "- user_value_agent: 用户价值 Agent（对照用户历史偏好）\n"
    "- comprehensive_agent: 综合 Agent（调度、停止规则判断与最终决策汇总）\n\n"
    "工作流程：\n"
    "1. 综合 Agent 依次调用三个分析 Agent\n"
    "2. 综合 Agent 调用 evaluate_stop 判断是否停止\n"
    "3. 收到停止信号后调用 finalize_decision 输出结论\n"
    "4. 输出最终报告后，回复 FINISH\n\n"
    f"硬性约束：最多 {MAX_ROUNDS} 轮分析，超过必须强制结束。"
)

# 创建 Supervisor Graph（recursion_limit 作为系统级硬停止保底）
graph = create_supervisor(
    agents=[comprehensive_agent, cost_analysis_agent, risk_assessment_agent, user_value_agent],
    model=llm,
    prompt=supervisor_prompt,
).with_config({"recursion_limit": MAX_ROUNDS * 10 + 5})
