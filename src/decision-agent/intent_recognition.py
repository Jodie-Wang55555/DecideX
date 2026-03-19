"""
意图识别与问题重写模块（Intent Recognition & Query Rewriting）

功能：
1. 对用户输入进行意图分类，识别决策类型
2. 将模糊表述重写为结构化意图标签 + 清晰决策问题
3. 提取多轮对话历史中的关键决策要素

意图标签体系：
- career_choice:    职业/工作选择
- investment:       投资/理财决策
- purchase:         消费/购买决策（房/车/产品）
- travel:           旅行/出行决策
- education:        学习/教育规划
- relationship:     人际/社交决策
- general:          通用决策
"""

import json
import re
import os
import sys
import requests

# 确保能找到上层模块
_ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

try:
    from langchain_google_genai import ChatGoogleGenerativeAI
    def _resolve_google_model() -> str:
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
            models = resp.json().get("models", [])
            candidates = []
            for m in models:
                if "generateContent" in (m.get("supportedGenerationMethods", []) or []):
                    name = (m.get("name") or "").split("/")[-1]
                    if name:
                        candidates.append(name)
            for preferred in ["gemini-2.5-flash", "gemini-2.5-pro", "gemini-2.0-flash", "gemini-1.5-pro", "gemini-1.5-flash"]:
                if preferred in candidates:
                    return preferred
            if candidates:
                return candidates[0]
        except Exception:
            pass
        return "gemini-2.5-flash"

    _llm = ChatGoogleGenerativeAI(
        model=_resolve_google_model(),
        temperature=0.0,
    )
except ImportError:
    from langchain_openai import ChatOpenAI
    _llm = ChatOpenAI(model="gpt-4o", temperature=0.0)

from langchain_core.messages import HumanMessage, SystemMessage


# ============================================================
# 意图分类体系
# ============================================================

INTENT_LABELS = {
    "career_choice":   "职业/工作选择（换工作、选专业、创业等）",
    "investment":      "投资/理财决策（股票、基金、房产投资等）",
    "purchase":        "消费/购买决策（买房、买车、大额消费等）",
    "travel":          "旅行/出行决策（目的地、同行人、行程等）",
    "education":       "学习/教育规划（选课、考证、留学等）",
    "relationship":    "人际/社交决策（合作、交友、处理关系等）",
    "general":         "通用决策（不属于以上类别）",
}

INTENT_SYSTEM_PROMPT = """你是一个决策意图分析专家。请分析用户输入，完成以下任务：

1. **意图分类**：从以下标签中选择最匹配的一个：
   - career_choice: 职业/工作选择
   - investment: 投资/理财决策
   - purchase: 消费/购买决策（买房、买车等）
   - travel: 旅行/出行决策
   - education: 学习/教育规划
   - relationship: 人际/社交决策
   - general: 通用决策

2. **问题重写**：将用户的模糊表述重写为清晰的结构化决策问题，包含：
   - 决策主体（谁在决策）
   - 候选方案（选项A vs 选项B）
   - 核心诉求（用户最关心什么）

3. **关键要素提取**：从输入中提取3-5个影响决策的关键要素

严格按以下JSON格式输出，不要添加任何额外文字：
{
  "intent_label": "标签名",
  "intent_desc": "一句话描述意图",
  "rewritten_query": "重写后的清晰决策问题",
  "key_factors": ["要素1", "要素2", "要素3"],
  "confidence": 0.0到1.0的浮点数
}"""


# ============================================================
# 核心函数
# ============================================================

def recognize_intent(user_input: str, conversation_history: list = None) -> dict:
    """
    对用户输入进行意图识别与问题重写。

    Args:
        user_input:           用户原始输入
        conversation_history: 多轮对话历史 [{"role": "user/assistant", "content": "..."}]

    Returns:
        {
            "intent_label": str,
            "intent_desc": str,
            "rewritten_query": str,
            "key_factors": list,
            "confidence": float,
            "original_query": str
        }
    """
    messages = [SystemMessage(content=INTENT_SYSTEM_PROMPT)]

    # 注入对话历史上下文（最近3轮）
    if conversation_history:
        history_text = "\n".join([
            f"{m['role'].upper()}: {m['content']}"
            for m in conversation_history[-6:]  # 最近3轮
        ])
        messages.append(HumanMessage(
            content=f"【对话历史】\n{history_text}\n\n【当前输入】\n{user_input}"
        ))
    else:
        messages.append(HumanMessage(content=user_input))

    try:
        response = _llm.invoke(messages)
        raw = response.content.strip()

        # 清理可能的 markdown 代码块
        raw = re.sub(r"```json\s*", "", raw)
        raw = re.sub(r"```\s*", "", raw)

        result = json.loads(raw)
        result["original_query"] = user_input
        return result

    except Exception as e:
        # 降级：返回默认意图
        return {
            "intent_label": "general",
            "intent_desc": "通用决策分析",
            "rewritten_query": user_input,
            "key_factors": [],
            "confidence": 0.5,
            "original_query": user_input,
        }


def format_intent_for_prompt(intent: dict) -> str:
    """将意图识别结果格式化为可注入 Agent Prompt 的文本"""
    label = intent.get("intent_label", "general")
    desc = intent.get("intent_desc", "")
    rewritten = intent.get("rewritten_query", intent.get("original_query", ""))
    factors = intent.get("key_factors", [])
    confidence = intent.get("confidence", 0.5)

    lines = [
        f"🎯 **意图识别结果**（置信度 {confidence:.0%}）",
        f"- 意图类型：{label}（{desc}）",
        f"- 结构化问题：{rewritten}",
    ]
    if factors:
        lines.append(f"- 关键决策要素：{'、'.join(factors)}")

    return "\n".join(lines)
