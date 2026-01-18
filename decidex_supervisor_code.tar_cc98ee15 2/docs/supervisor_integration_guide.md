# 综合决策 Agent 集成指南

## 核心概念

综合决策 Agent **不是独立运行的 Agent**，而是一个**决策汇总模块**，它接收来自三个分析 Agent 的输出，然后生成最终决策。

## 数据流

```
用户输入问题
    ↓
┌─────────────┐
│ 成本分析 Agent │ → 成本分析结果（字符串）
└─────────────┘
    ↓
┌─────────────┐
│ 风险评估 Agent │ → 风险评估结果（字符串）
└─────────────┘
    ↓
┌─────────────┐
│ 用户价值 Agent │ → 用户价值分析结果（字符串）
└─────────────┘
    ↓
┌─────────────┐
│ 综合决策 Agent │ → 最终决策（唯一、明确、不可回退）
└─────────────┘
```

## 集成方式

### 方式 1：直接调用（推荐）

```python
import asyncio
from src.agents.supervisor_agent import SupervisorAgent

async def make_decision():
    # 1. 创建综合决策 Agent
    supervisor = SupervisorAgent()

    # 2. 调用你的三个 Agent 获取分析结果
    cost_result = await your_cost_agent.analyze(query, options)
    risk_result = await your_risk_agent.analyze(query, options)
    value_result = await your_value_agent.analyze(query, options)

    # 3. 将结果传递给综合决策 Agent
    decision = await supervisor.make_decision(
        cost_analysis=cost_result,
        risk_analysis=risk_result,
        value_analysis=value_result,
        current_round=1
    )

    # 4. 获取最终决策
    print(decision['final_decision'])
    return decision

asyncio.run(make_decision())
```

### 方式 2：多轮分析

```python
async def multi_round_decision():
    supervisor = SupervisorAgent()

    current_round = 1
    max_rounds = 2

    while current_round <= max_rounds:
        # 每一轮都调用三个 Agent
        cost_result = await your_cost_agent.analyze(query, options)
        risk_result = await your_risk_agent.analyze(query, options)
        value_result = await your_value_agent.analyze(query, options)

        # 调用综合决策 Agent
        decision = await supervisor.make_decision(
            cost_analysis=cost_result,
            risk_analysis=risk_result,
            value_analysis=value_result,
            current_round=current_round
        )

        # 判断是否应该停止
        if decision['should_stop']:
            print(f"终止原因：{decision['stop_reason']}")
            print(decision['final_decision'])
            break

        current_round += 1

    return decision
```

## 输入要求

综合决策 Agent 接收三个字符串参数，格式要求如下：

### 1. 成本分析 (cost_analysis)

```markdown
## 💰 成本分析

### 选项1：[选项名称]
- 时间成本：[评估]
- 金钱成本：[评估]
- 资源成本：[评估]
- 机会成本：[评估]
- **综合成本评分**：[0~10]

### 选项2：[选项名称]
[同上格式]

### 💡 成本维度推荐
从成本角度，我建议优先考虑：[选项名称]
**理由**：[1-2 句话]
```

### 2. 风险评估 (risk_analysis)

```markdown
## ⚠️ 风险评估

### 选项1：[选项名称]
- 不确定性因素：[列出]
- 最坏情况：[描述]
- 失败概率：[高/中/低]
- 可逆性：[可逆/部分可逆/不可逆]
- **综合风险评分**：[0~10]

### 选项2：[选项名称]
[同上格式]

### 💡 风险维度推荐
从风险角度，我建议优先考虑：[选项名称]
**理由**：[1-2 句话]
```

### 3. 用户价值分析 (value_analysis)

```markdown
## 💎 价值匹配分析

### 选项1：[选项名称]
- 成就导向：[匹配度 0~10，说明]
- 安全感：[匹配度 0~10，说明]
- 自主性：[匹配度 0~10，说明]
- 关系导向：[匹配度 0~10，说明]
- **综合价值评分**：[0~10]

### 选项2：[选项名称]
[同上格式]

### 💡 价值维度推荐
从用户价值观角度，我建议优先考虑：[选项名称]
**理由**：[1-2 句话]
```

## 输出格式

综合决策 Agent 返回一个字典：

```python
{
    "should_stop": bool,        # 是否应该停止分析
    "stop_reason": str,         # 停止原因
    "current_round": int,       # 当前轮次
    "cost_analysis": str,       # 成本分析结果
    "risk_analysis": str,       # 风险评估结果
    "value_analysis": str,      # 用户价值分析结果
    "final_decision": str,      # 最终决策内容（Markdown 格式）
    "agent_results": dict       # 所有 Agent 的结果
}
```

### 最终决策内容示例

```markdown
### 📊 综合分析
[三个维度的汇总分析]

### 🎯 最终决策建议
**优先选择：[选项名称]**

**核心理由**：
1. [理由1]
2. [理由2]
3. [理由3]

**补充行动建议**：
[1-2 条具体建议]
```

## 终止规则

综合决策 Agent 会根据以下规则判断是否应该停止分析：

### 1. 硬停止规则（必须执行）
- **最大轮次限制**：分析轮次达到 2 轮时，必须停止
- **返回**：`should_stop=True, stop_reason="已达到最大分析轮次 2，必须给出最终决策"`

### 2. 收敛停止规则（推荐执行）
- **结果稳定性**：当多个 Agent 的结果高度一致时，可以停止
- **返回**：`should_stop=True, stop_reason="各维度分析结果已趋于稳定"`

### 3. 低收益停止规则（谨慎执行）
- **信息增量**：当新增信息很少时，建议停止
- **返回**：`should_stop=True, stop_reason="本轮新增信息量不足，建议终止分析"`

### 4. 继续分析（第一轮）
- **第一轮分析**：默认继续分析，需要更多信息
- **返回**：`should_stop=False, stop_reason="第一轮分析完成，需要更多信息支持决策"`

## 完整示例代码

```python
import asyncio
from src.agents.supervisor_agent import SupervisorAgent

# 假设你已经实现了三个 Agent
async def your_cost_agent(query, options):
    """你的成本分析 Agent"""
    # 实现你的成本分析逻辑
    return cost_result

async def your_risk_agent(query, options):
    """你的风险评估 Agent"""
    # 实现你的风险评估逻辑
    return risk_result

async def your_value_agent(query, options):
    """你的用户价值 Agent"""
    # 实现你的用户价值分析逻辑
    return value_result


async def main():
    # 用户输入
    query = "我在当前公司工作了3年，工作稳定但发展空间有限..."
    options = ["跳槽到新公司", "留在原公司", "继续观望"]

    # 创建综合决策 Agent
    supervisor = SupervisorAgent()

    # 调用三个 Agent
    cost_result = await your_cost_agent(query, options)
    risk_result = await your_risk_agent(query, options)
    value_result = await your_value_agent(query, options)

    # 综合决策
    decision = await supervisor.make_decision(
        cost_analysis=cost_result,
        risk_analysis=risk_result,
        value_analysis=value_result,
        current_round=1
    )

    # 输出结果
    print(decision['final_decision'])
    print(f"\n是否应该停止：{decision['should_stop']}")
    print(f"停止原因：{decision['stop_reason']}")

asyncio.run(main())
```

## 常见问题

### Q1: 我的 Agent 输出格式不完全符合要求怎么办？

A: 综合决策 Agent 有一定的容错能力，能够处理各种格式的输入。但为了获得最佳效果，建议：
- 包含各选项的评估结果
- 包含维度推荐
- 使用 Markdown 格式

### Q2: 可以只用两个 Agent 吗？

A: 理论上可以，但综合决策 Agent 期望接收三个维度的输入。如果只有两个，可以：
- 让缺失的维度返回"该维度无法评估"或空字符串
- 或者在调用前填充默认值

### Q3: 综合决策 Agent 会修改输入吗？

A: 不会。综合决策 Agent 只会读取输入，不会修改原始数据。

### Q4: 如何调整终止规则的参数？

A: 修改 `config/decidex_config.json` 中的 `stopping_rules` 部分。

### Q5: 综合决策 Agent 的输出可以用于 Arduino 硬件吗？

A: 可以。解析最终决策中的推荐选项，提取选项编号或名称，然后发送给 Arduino：

```python
# 提取推荐的选项
import re
decision_text = decision['final_decision']
match = re.search(r'优先选择[:：]\s*(.*?)(?:\n|$)', decision_text)
if match:
    option = match.group(1).strip()
    # 发送给 Arduino
    send_to_arduino(option)
```

## 测试

运行集成测试：

```bash
python tests/test_supervisor_integration.py
```

运行集成示例：

```bash
python examples/integration_example.py
```

## 总结

综合决策 Agent 的设计理念：
- ✅ **独立性**：不依赖其他 Agent 的代码实现
- ✅ **灵活性**：接收字符串输入，可以与任何 Agent 集成
- ✅ **明确性**：输出唯一、明确、不可回退的决策
- ✅ **智能终止**：自动判断何时停止分析

你只需要确保你的三个 Agent 输出符合格式要求，然后按照集成方式调用综合决策 Agent 即可。
