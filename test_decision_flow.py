"""
测试 DecideX 决策系统完整流程
模拟：用户输入决策问题 → 三个 Agent 生成问题 → 用户回答 → Supervisor 给出建议
"""

import asyncio
from langchain_core.messages import HumanMessage
from src.decision_agent.graph import (
    cost_analysis_agent,
    risk_assessment_agent,
    user_value_agent,
    comprehensive_agent
)

async def test_decision_flow():
    """测试决策流程"""
    
    # 用户的问题
    user_question = "我朋友约我出去旅游，但是我有一个考试，我应该去旅游嘛"
    
    print("=" * 80)
    print("🤔 用户问题：")
    print(f"{user_question}\n")
    print("=" * 80)
    
    # 步骤1：让三个 Agent 分别生成前置问题
    print("\n📋 步骤1: 三个 Agent 生成前置问题\n")
    
    # 1.1 成本分析 Agent 生成问题
    print("-" * 80)
    print("💰 成本分析 Agent 的问题：")
    print("-" * 80)
    
    cost_response = await cost_analysis_agent.ainvoke({
        "messages": [HumanMessage(content=user_question)]
    })
    
    cost_questions = cost_response.get("messages", [])[-1].content if hasattr(cost_response, "get") else str(cost_response)
    print(cost_questions)
    print()
    
    # 1.2 风险评估 Agent 生成问题
    print("-" * 80)
    print("⚠️  风险评估 Agent 的问题：")
    print("-" * 80)
    
    risk_response = await risk_assessment_agent.ainvoke({
        "messages": [HumanMessage(content=user_question)]
    })
    
    risk_questions = risk_response.get("messages", [])[-1].content if hasattr(risk_response, "get") else str(risk_response)
    print(risk_questions)
    print()
    
    # 1.3 用户价值 Agent 生成问题
    print("-" * 80)
    print("💎 用户价值 Agent 的问题：")
    print("-" * 80)
    
    value_response = await user_value_agent.ainvoke({
        "messages": [HumanMessage(content=user_question)]
    })
    
    value_questions = value_response.get("messages", [])[-1].content if hasattr(value_response, "get") else str(value_response)
    print(value_questions)
    print()
    
    # 步骤2：模拟用户回答（这里我们用预设的答案）
    print("=" * 80)
    print("📝 步骤2: 模拟用户回答\n")
    
    # 模拟用户回答（基于常见情况）
    user_answers = """
    成本分析相关问题回答：
    - 朋友主动提议，2-3人一起去旅行
    - 旅行预算约5000元
    - 旅行需要3天时间
    - 考试需要1周准备时间
    
    风险评估相关问题回答：
    - 朋友很可靠，不会爽约
    - 如果考试失败，可以补考但会影响毕业时间
    - 我的风险承受能力中等
    
    用户价值相关问题回答：
    - 我很看重友谊和放松
    - 但也很重视学业和未来规划
    - 希望找到平衡点
    """
    
    print(user_answers)
    print()
    
    # 步骤3：基于回答，让三个 Agent 进行分析
    print("=" * 80)
    print("📊 步骤3: 三个 Agent 进行分析\n")
    
    analysis_context = f"""
    用户问题：{user_question}
    
    用户回答：
    {user_answers}
    """
    
    # 3.1 成本分析
    print("-" * 80)
    print("💰 成本分析结果：")
    print("-" * 80)
    
    cost_analysis = await cost_analysis_agent.ainvoke({
        "messages": [HumanMessage(content=analysis_context)]
    })
    
    cost_result = cost_analysis.get("messages", [])[-1].content if hasattr(cost_analysis, "get") else str(cost_analysis)
    print(cost_result)
    print()
    
    # 3.2 风险评估
    print("-" * 80)
    print("⚠️  风险评估结果：")
    print("-" * 80)
    
    risk_analysis = await risk_assessment_agent.ainvoke({
        "messages": [HumanMessage(content=analysis_context)]
    })
    
    risk_result = risk_analysis.get("messages", [])[-1].content if hasattr(risk_analysis, "get") else str(risk_analysis)
    print(risk_result)
    print()
    
    # 3.3 用户价值分析
    print("-" * 80)
    print("💎 用户价值分析结果：")
    print("-" * 80)
    
    value_analysis = await user_value_agent.ainvoke({
        "messages": [HumanMessage(content=analysis_context)]
    })
    
    value_result = value_analysis.get("messages", [])[-1].content if hasattr(value_analysis, "get") else str(value_analysis)
    print(value_result)
    print()
    
    # 步骤4：Supervisor 综合决策
    print("=" * 80)
    print("🎯 步骤4: Supervisor 综合决策\n")
    print("-" * 80)
    
    supervisor_context = f"""
    请基于以下三个维度的分析结果，做出最终决策：
    
    ## 成本分析结果：
    {cost_result}
    
    ## 风险评估结果：
    {risk_result}
    
    ## 用户价值分析结果：
    {value_result}
    
    请给出综合分析和最终决策建议。
    """
    
    supervisor_decision = await comprehensive_agent.ainvoke({
        "messages": [HumanMessage(content=supervisor_context)]
    })
    
    final_decision = supervisor_decision.get("messages", [])[-1].content if hasattr(supervisor_decision, "get") else str(supervisor_decision)
    print(final_decision)
    print()
    
    print("=" * 80)
    print("✅ 测试完成！")
    print("=" * 80)

if __name__ == "__main__":
    asyncio.run(test_decision_flow())
