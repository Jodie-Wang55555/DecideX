"""
模拟测试 DecideX 决策系统流程
注意：此脚本仅模拟流程结构，实际运行需要配置 OPENAI_API_KEY
"""

import asyncio
from langchain_core.messages import HumanMessage

def simulate_agent_response(agent_name: str, question: str) -> str:
    """模拟 Agent 的响应（不实际调用 LLM）"""
    
    if "成本分析" in agent_name or "cost" in agent_name.lower():
        return """{
  "type": "precondition_questions",
  "message": "为了给你提供精准的成本分析，请快速选择以下问题",
  "questions": [
    {
      "id": 1,
      "question": "朋友是否明确表示愿意去？",
      "options": [
        {"key": "A", "label": "主动提议"},
        {"key": "B", "label": "被动接受"},
        {"key": "C", "label": "犹豫不决"}
      ]
    },
    {
      "id": 2,
      "question": "你和几个朋友一起去旅行？",
      "options": [
        {"key": "A", "label": "1人"},
        {"key": "B", "label": "2-3人"},
        {"key": "C", "label": "4人以上"}
      ]
    },
    {
      "id": 3,
      "question": "旅行预算大概是多少？",
      "options": [
        {"key": "A", "label": "2000元以下"},
        {"key": "B", "label": "2000-5000元"},
        {"key": "C", "label": "5000元以上"}
      ]
    },
    {
      "id": 4,
      "question": "考试距离现在还有多长时间？",
      "options": [
        {"key": "A", "label": "1周以内"},
        {"key": "B", "label": "1-2周"},
        {"key": "C", "label": "2周以上"}
      ]
    }
  ]
}"""
    
    elif "风险评估" in agent_name or "risk" in agent_name.lower():
        return """{
  "type": "precondition_questions",
  "message": "为了给你提供精准的风险评估，请快速选择以下问题",
  "questions": [
    {
      "id": 1,
      "question": "对方的可靠性如何？",
      "options": [
        {"key": "A", "label": "非常可靠"},
        {"key": "B", "label": "比较可靠"},
        {"key": "C", "label": "一般"}
      ]
    },
    {
      "id": 2,
      "question": "如果考试失败，你能承受的后果？",
      "options": [
        {"key": "A", "label": "可以补考，影响不大"},
        {"key": "B", "label": "影响毕业时间"},
        {"key": "C", "label": "后果严重"}
      ]
    },
    {
      "id": 3,
      "question": "你的风险承受能力如何？",
      "options": [
        {"key": "A", "label": "强"},
        {"key": "B", "label": "中等"},
        {"key": "C", "label": "弱"}
      ]
    },
    {
      "id": 4,
      "question": "如果旅行中出问题，朋友会承担责任吗？",
      "options": [
        {"key": "A", "label": "会"},
        {"key": "B", "label": "部分会"},
        {"key": "C", "label": "不会"}
      ]
    }
  ]
}"""
    
    elif "用户价值" in agent_name or "value" in agent_name.lower():
        return """{
  "type": "precondition_questions",
  "message": "为了给你提供精准的用户价值分析，请快速选择以下问题",
  "questions": [
    {
      "id": 1,
      "question": "友谊和放松对你的重要性？",
      "options": [
        {"key": "A", "label": "非常重要"},
        {"key": "B", "label": "比较重要"},
        {"key": "C", "label": "一般"}
      ]
    },
    {
      "id": 2,
      "question": "学业和未来规划对你的重要性？",
      "options": [
        {"key": "A", "label": "非常重要"},
        {"key": "B", "label": "比较重要"},
        {"key": "C", "label": "一般"}
      ]
    },
    {
      "id": 3,
      "question": "你更看重哪个？",
      "options": [
        {"key": "A", "label": "友谊和社交"},
        {"key": "B", "label": "学业和成就"},
        {"key": "C", "label": "两者平衡"}
      ]
    },
    {
      "id": 4,
      "question": "你通常如何做出类似决策？",
      "options": [
        {"key": "A", "label": "优先考虑情感"},
        {"key": "B", "label": "优先考虑理性"},
        {"key": "C", "label": "综合考虑"}
      ]
    }
  ]
}"""
    
    return "问题生成中..."

def print_section(title: str):
    """打印分节标题"""
    print("\n" + "=" * 80)
    print(f"  {title}")
    print("=" * 80)

def print_subsection(title: str):
    """打印子节标题"""
    print("\n" + "-" * 80)
    print(f"  {title}")
    print("-" * 80)

def main():
    """主测试流程"""
    
    # 用户问题
    user_question = "我朋友约我出去旅游，但是我有一个考试，我应该去旅游嘛"
    
    print_section("🤔 用户问题")
    print(f"\n{user_question}\n")
    
    # 步骤1：三个 Agent 生成问题
    print_section("📋 步骤1: 三个 Agent 生成前置问题")
    
    print_subsection("💰 成本分析 Agent 的问题")
    cost_questions = simulate_agent_response("成本分析Agent", user_question)
    print(cost_questions)
    
    print_subsection("⚠️  风险评估 Agent 的问题")
    risk_questions = simulate_agent_response("风险评估Agent", user_question)
    print(risk_questions)
    
    print_subsection("💎 用户价值 Agent 的问题")
    value_questions = simulate_agent_response("用户价值Agent", user_question)
    print(value_questions)
    
    # 步骤2：模拟用户回答
    print_section("📝 步骤2: 模拟用户回答")
    
    user_answers = """
    成本分析相关问题回答：
    - 朋友主动提议，2-3人一起去旅行 (问题1: A, 问题2: B)
    - 旅行预算约3000-5000元 (问题3: B)
    - 考试距离现在还有1-2周时间 (问题4: B)
    
    风险评估相关问题回答：
    - 朋友非常可靠 (问题1: A)
    - 如果考试失败，可以补考但会影响毕业时间 (问题2: B)
    - 我的风险承受能力中等 (问题3: B)
    - 朋友会承担责任 (问题4: A)
    
    用户价值相关问题回答：
    - 友谊和放松对我非常重要 (问题1: A)
    - 学业和未来规划也非常重要 (问题2: A)
    - 我更看重两者平衡 (问题3: C)
    - 我通常综合考虑 (问题4: C)
    """
    print(user_answers)
    
    # 步骤3：三个 Agent 进行分析（模拟结果）
    print_section("📊 步骤3: 三个 Agent 进行分析")
    
    print_subsection("💰 成本分析结果")
    print("""
### 📊 成本总览
| 方案 | 显性成本 | 隐性成本 | 综合成本评级 |
|------|----------|----------|--------------|
| 去旅游 | ¥3000-5000 / 3-5天 | 中 | ⭐⭐ |
| 准备考试 | ¥0 / 7-10天 | 高 | ⭐⭐⭐ |

### 💰 显性成本详细分析
**去旅游**
- 金钱成本：3000-5000元（交通、住宿、餐饮）
- 时间成本：3-5天旅行时间 + 准备时间
- 资源成本：中等

**准备考试**
- 金钱成本：几乎为0
- 时间成本：7-10天专心准备
- 资源成本：低

### 🎭 隐性成本评估
**机会成本**：去旅游会占用考试准备时间，可能影响考试成绩
**心理成本**：不去可能影响友谊，去了可能担心考试
**维护/后续成本**：考试失败可能需要补考，影响毕业时间
""")
    
    print_subsection("⚠️  风险评估结果")
    print("""
### ⚠️ 风险总览
| 方案 | 不确定性等级 | 失败后果 | 综合风险评级 |
|------|--------------|----------|--------------|
| 去旅游 | 中 | 中等 | ⭐⭐ |
| 准备考试 | 低 | 低 | ⭐ |

### 🌪️ 不确定性因素分析
**去旅游**
- 内部不确定性：考试准备是否充分取决于当前基础
- 外部不确定性：旅行是否顺利，是否有意外
- 不可控因素：旅行中的突发情况

**准备考试**
- 内部不确定性：个人准备效率
- 外部不确定性：考试难度
- 不可控因素：较少

### 💥 失败后果评估
**直接后果**：考试失败可能影响毕业时间（但可以补考）
**间接后果**：不去旅行可能影响友谊关系
""")
    
    print_subsection("💎 用户价值分析结果")
    print("""
### 💎 核心价值观
- **友谊和社交**：高重要性
- **学业和成就**：高重要性
- **平衡生活**：追求两者平衡

### 📊 价值观维度分析
| 价值观维度 | 重要性 | 具体表现 |
|-----------|-------|---------|
| 关系导向 | 高 | 重视友谊，和朋友的关系很好 |
| 成就导向 | 高 | 重视学业，希望顺利毕业 |
| 平衡导向 | 高 | 希望在友谊和学业间找到平衡 |

### 🎯 价值观洞察
用户同时重视友谊和学业，希望在两者间找到平衡点。
""")
    
    # 步骤4：Supervisor 综合决策
    print_section("🎯 步骤4: Supervisor 综合决策")
    
    print("""
### 📊 多维分析汇总
**成本维度分析**：
去旅游需要3000-5000元和3-5天时间，而准备考试几乎无金钱成本但需要7-10天。从成本角度看，准备考试更经济。

**风险维度分析**：
去旅游的风险中等，主要是不确定性；准备考试的风险较低。从风险角度看，准备考试更安全。

**用户价值维度分析**：
用户同时重视友谊和学业，希望在两者间找到平衡。去旅游能满足友谊需求，准备考试能满足学业需求。

### 🎯 终止判断
**当前轮次**：第 1 轮 / 最大 2 轮
**判断结果**：满足终止条件
**终止原因**：信息已充分，三个维度的分析结果明确

### ✅ 最终决策建议
**我建议你选择：与朋友协商，寻找折中方案**

**理由**：
1. **时间协调**：考试还有1-2周时间，可以与朋友协商将旅行时间调整到考试之后，既能维护友谊，又不影响考试准备
2. **价值平衡**：这样的安排同时满足了友谊和学业两个重要价值维度
3. **风险最小化**：既避免了考试失败的风险，也避免了友谊受损的风险

**行动建议**：
1. 主动与朋友沟通，说明考试的重要性，建议将旅行安排到考试结束后
2. 如果朋友坚持原计划，可以考虑旅行2-3天后提前返回，确保有足够时间准备考试
3. 在旅行期间，可以带上学习资料，利用碎片时间复习

---

## 说明
- 本决策基于成本、风险、用户价值三个维度的综合分析
- 决策已做出，建议你接受并执行，而非继续比较
- 如果执行后发现问题，可以作为下次决策的经验
""")
    
    print_section("✅ 测试完成")
    print("\n注意：这是模拟测试，展示了系统的完整流程。")
    print("实际运行需要配置 OPENAI_API_KEY 并调用真实的 LLM。\n")

if __name__ == "__main__":
    main()
