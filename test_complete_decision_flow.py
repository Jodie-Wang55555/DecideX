"""
完整测试 DecideX 决策系统 - 完整流程
1. 三个 Agent 生成问题
2. 模拟用户回答
3. 三个 Agent 进行分析
4. Supervisor 给出最终建议
"""

import asyncio
import os
import sys
from dotenv import load_dotenv
from langchain_core.messages import HumanMessage

# 加载环境变量
load_dotenv()

# 添加 src 到路径
sys.path.insert(0, 'src')

try:
    from langchain_google_genai import ChatGoogleGenerativeAI
    USE_GOOGLE = True
except ImportError:
    from langchain_openai import ChatOpenAI
    USE_GOOGLE = False

# 导入三个 Agent（从 Swarm graph）
import importlib.util
swarm_spec = importlib.util.spec_from_file_location("swarm_graph", "src/swarm/graph.py")
swarm_module = importlib.util.module_from_spec(swarm_spec)
swarm_spec.loader.exec_module(swarm_module)

cost_analysis_agent = swarm_module.swarm_agent1
risk_assessment_agent = swarm_module.swarm_agent2
user_value_agent = swarm_module.swarm_agent3

# 导入 Supervisor（从 decision-agent）
decision_spec = importlib.util.spec_from_file_location("decision_graph", "src/decision-agent/graph.py")
decision_module = importlib.util.module_from_spec(decision_spec)
decision_spec.loader.exec_module(decision_module)

comprehensive_agent = decision_module.comprehensive_agent

def print_section(title: str):
    """打印分节标题"""
    print("\n" + "=" * 80)
    print(f"  {title}")
    print("=" * 80 + "\n")

def print_subsection(title: str):
    """打印子节标题"""
    print("\n" + "-" * 80)
    print(f"  {title}")
    print("-" * 80 + "\n")

async def extract_response_content(response):
    """提取响应内容"""
    if isinstance(response, dict) and "messages" in response:
        messages = response["messages"]
        if messages:
            last_msg = messages[-1]
            if hasattr(last_msg, "content"):
                content = last_msg.content
                # 如果是列表，提取文本
                if isinstance(content, list):
                    for item in content:
                        if isinstance(item, dict) and "text" in item:
                            return item["text"]
                return str(content)
    return str(response)

async def test_complete_flow():
    """完整测试流程"""
    
    user_question = "我朋友约我出去旅游，但是我有一个考试，我应该去旅游嘛"
    
    print_section("🤔 步骤1: 用户输入决策问题")
    print(user_question)
    
    # ========================================================================
    # 步骤2：三个 Agent 分别生成问题
    # ========================================================================
    print_section("📋 步骤2: 三个 Agent 生成前置问题")
    
    # 2.1 成本分析 Agent
    print_subsection("💰 成本分析 Agent 生成的问题")
    try:
        cost_questions_resp = await cost_analysis_agent.ainvoke({
            "messages": [HumanMessage(content=user_question)]
        })
        cost_questions = await extract_response_content(cost_questions_resp)
        print(cost_questions)
    except Exception as e:
        print(f"❌ 错误: {str(e)[:200]}")
        cost_questions = "成本分析问题生成失败"
    
    # 2.2 风险评估 Agent
    print_subsection("⚠️  风险评估 Agent 生成的问题")
    try:
        risk_questions_resp = await risk_assessment_agent.ainvoke({
            "messages": [HumanMessage(content=user_question)]
        })
        risk_questions = await extract_response_content(risk_questions_resp)
        print(risk_questions)
    except Exception as e:
        print(f"❌ 错误: {str(e)[:200]}")
        risk_questions = "风险评估问题生成失败"
    
    # 2.3 用户价值 Agent
    print_subsection("💎 用户价值 Agent 生成的问题")
    try:
        value_questions_resp = await user_value_agent.ainvoke({
            "messages": [HumanMessage(content=user_question)]
        })
        value_questions = await extract_response_content(value_questions_resp)
        print(value_questions)
    except Exception as e:
        print(f"❌ 错误: {str(e)[:200]}")
        value_questions = "用户价值问题生成失败"
    
    # ========================================================================
    # 步骤3：模拟用户回答（基于常见情况预设答案）
    # ========================================================================
    print_section("📝 步骤3: 模拟用户回答所有问题")
    
    user_answers = """
    基于问题的回答：
    
    【成本分析相关问题】
    - 需要在未来3天内做出决定
    - 考试比较重要（影响课程绩点）
    - 这是好朋友，是一次常规的旅行邀约
    - 预算适中，在我的承受范围之内
    - 旅行时间可以商量，但考试时间固定
    
    【风险评估相关问题】
    - 朋友非常可靠
    - 如果考试失败，影响课程绩点，但可以补考
    - 我的风险承受能力中等
    - 如果旅行中出问题，朋友会承担责任
    
    【用户价值相关问题】
    - 友谊和放松对我比较重要
    - 学业和未来规划非常重要
    - 我更看重两者平衡
    - 我通常综合考虑
    """
    
    print(user_answers)
    
    # ========================================================================
    # 步骤4：三个 Agent 基于回答进行分析
    # ========================================================================
    print_section("📊 步骤4: 三个 Agent 基于回答进行分析")
    
    analysis_context = f"""
    原始问题：{user_question}
    
    用户回答：
    {user_answers}
    
    请基于以上信息，进行详细分析并给出分析报告。
    """
    
    # 4.1 成本分析
    print_subsection("💰 成本分析结果")
    try:
        cost_analysis_resp = await cost_analysis_agent.ainvoke({
            "messages": [HumanMessage(content=analysis_context)]
        })
        cost_analysis = await extract_response_content(cost_analysis_resp)
        print(cost_analysis)
    except Exception as e:
        print(f"❌ 错误: {str(e)[:200]}")
        cost_analysis = "成本分析失败"
    
    # 4.2 风险评估
    print_subsection("⚠️  风险评估结果")
    try:
        risk_analysis_resp = await risk_assessment_agent.ainvoke({
            "messages": [HumanMessage(content=analysis_context)]
        })
        risk_analysis = await extract_response_content(risk_analysis_resp)
        print(risk_analysis)
    except Exception as e:
        print(f"❌ 错误: {str(e)[:200]}")
        risk_analysis = "风险评估失败"
    
    # 4.3 用户价值分析
    print_subsection("💎 用户价值分析结果")
    try:
        value_analysis_resp = await user_value_agent.ainvoke({
            "messages": [HumanMessage(content=analysis_context)]
        })
        value_analysis = await extract_response_content(value_analysis_resp)
        print(value_analysis)
    except Exception as e:
        print(f"❌ 错误: {str(e)[:200]}")
        value_analysis = "用户价值分析失败"
    
    # ========================================================================
    # 步骤5：Supervisor 综合决策
    # ========================================================================
    print_section("🎯 步骤5: Supervisor 综合决策")
    
    supervisor_context = f"""请基于以下三个维度的分析结果，做出最终决策：

## 成本分析结果：
{cost_analysis}

## 风险评估结果：
{risk_analysis}

## 用户价值分析结果：
{value_analysis}

请给出综合分析摘要和最终决策建议，包括：
1. 多维分析汇总
2. 终止判断
3. 最终决策建议（明确选择一个方案，不要模糊）
"""
    
    print_subsection("✅ Supervisor 最终决策")
    try:
        supervisor_resp = await comprehensive_agent.ainvoke({
            "messages": [HumanMessage(content=supervisor_context)]
        })
        final_decision = await extract_response_content(supervisor_resp)
        print(final_decision)
    except Exception as e:
        print(f"❌ 错误: {str(e)[:200]}")
        import traceback
        traceback.print_exc()
        final_decision = "Supervisor 决策失败"
    
    # ========================================================================
    # 总结
    # ========================================================================
    print_section("✅ 完整测试流程结束")
    print("所有步骤已完成！")

if __name__ == "__main__":
    asyncio.run(test_complete_flow())
