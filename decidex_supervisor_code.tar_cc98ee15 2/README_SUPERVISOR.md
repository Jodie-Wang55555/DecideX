# DecideX 综合决策 Agent（独立版）

## 项目简介

这是 DecideX 项目的**综合决策 Agent**，负责汇总成本分析、风险评估、用户价值三个维度的分析结果，并给出唯一、明确、不可回退的最终决策。

## 核心功能

### 1. 汇总分析结果
接收并整合来自三个维度的分析结果：
- **成本分析**：时间、金钱、资源成本
- **风险评估**：不确定性、失败概率、可逆性
- **用户价值**：与用户价值观的匹配度

### 2. 终止判断
实现三种终止规则判断何时停止分析：

#### 硬停止规则（必须执行）
- 最大轮次限制：最多 2 轮分析
- 时间限制：单次分析超过 30 秒强制停止

#### 收敛停止规则（推荐执行）
- 评分收敛：Top1 选项连续两轮保持不变，且领先优势 ≥ 0.12
- 观点趋同：争议点数量 ≤ 1 个

#### 低收益停止规则（谨慎执行）
- 新信息增量 < 0.2（按 0~1 归一化）
- 重复率 ≥ 0.8

### 3. 综合决策
- 在信息充足时做出明确决策
- 在信息不足时给出"合理假设下的最优选择"
- 用清晰、有力、不可回退的语气表达决策结果

## 项目结构

```
.
├── config/
│   └── decidex_config.json        # 系统配置
├── src/
│   └── agents/
│       ├── __init__.py
│       └── supervisor_agent.py    # 综合决策 Agent（唯一保留）
└── tests/
    └── test_supervisor_integration.py  # 集成测试
```

## 快速开始

### 1. 运行测试

```bash
python tests/test_supervisor_integration.py
```

测试内容包括：
- ✅ 接收和处理三个维度的分析结果
- ✅ 生成最终决策
- ✅ 多轮分析场景下的终止判断

### 2. 使用综合决策 Agent

```python
import asyncio
from src.agents.supervisor_agent import SupervisorAgent

async def main():
    # 创建综合决策 Agent
    supervisor = SupervisorAgent()

    # 输入数据（来自其他 Agent 或用户）
    cost_analysis = """
    ## 成本分析
    选项A成本较低...
    选项B成本较高...
    """

    risk_analysis = """
    ## 风险评估
    选项A风险低...
    选项B风险高...
    """

    value_analysis = """
    ## 用户价值分析
    选项A更符合价值观...
    """

    # 做出决策
    decision_result = await supervisor.make_decision(
        cost_analysis=cost_analysis,
        risk_analysis=risk_analysis,
        value_analysis=value_analysis,
        current_round=1
    )

    # 获取决策
    print(decision_result['final_decision'])
    print(f"是否应该停止：{decision_result['should_stop']}")
    print(f"停止原因：{decision_result['stop_reason']}")

asyncio.run(main())
```

### 3. 终止判断

```python
from src.agents.supervisor_agent import SupervisorAgent

supervisor = SupervisorAgent()

# 判断是否应该停止分析
should_stop, reason = supervisor.should_stop_analysis(
    current_round=1,
    previous_results=None,
    current_results={
        "cost": "成本分析结果",
        "risk": "风险评估结果",
        "value": "用户价值分析结果"
    }
)

print(f"是否应该停止：{should_stop}")
print(f"原因：{reason}")
```

## 配置说明

`config/decidex_config.json` 包含系统的核心配置：

```json
{
    "model": "doubao-seed-1-8-251228",
    "temperature": 0.3,
    "max_completion_tokens": 4000,
    "timeout": 600,
    "thinking": "disabled",

    "stopping_rules": {
        "max_rounds": 2,
        "convergence_margin": 0.12,
        "min_new_info_threshold": 0.2
    }
}
```

**参数说明：**
- `model`: 使用的 LLM 模型
- `temperature`: 温度参数（0.3 表示更确定性的输出）
- `max_rounds`: 最大分析轮次（硬停止规则）
- `convergence_margin`: 收敛阈值（收敛停止规则）
- `min_new_info_threshold`: 最小新信息阈值（低收益停止规则）

## 输入输出格式

### 输入

综合决策 Agent 接收三个字符串参数：

1. `cost_analysis` (str): 成本分析结果
   - 包含各选项的成本评估
   - 包含成本维度的推荐

2. `risk_analysis` (str): 风险评估结果
   - 包含各选项的风险评估
   - 包含风险维度的推荐

3. `value_analysis` (str): 用户价值分析结果
   - 包含各选项与用户价值观的匹配度
   - 包含价值维度的推荐

4. `current_round` (int): 当前分析轮次

5. `previous_results` (dict | None): 上一轮的分析结果（可选）

### 输出

返回一个字典，包含以下字段：

```python
{
    "should_stop": bool,        # 是否应该停止分析
    "stop_reason": str,         # 停止原因
    "current_round": int,       # 当前轮次
    "cost_analysis": str,       # 成本分析结果
    "risk_analysis": str,       # 风险评估结果
    "value_analysis": str,      # 用户价值分析结果
    "final_decision": str,      # 最终决策内容
    "agent_results": dict       # 所有 Agent 的结果
}
```

## 决策输出格式

最终决策采用 Markdown 格式，包含以下部分：

### 📊 综合分析
- 多维分析汇总（成本、风险、用户价值）
- 综合维度评分汇总表
- 核心维度匹配结论

### 🎯 最终决策建议
- **优先选择**：[选项名称]
- **核心理由**：[1-3 条理由]
- **补充行动建议**：[1-2 条建议]

### ❓ 是否需要补充信息（可选）
- 如果信息不足，提示需要补充的信息

## 设计原则

### 1. 唯一性原则
- 只能给出一个最终决策
- 不能给出"建议 A 和 B 都可以考虑"的模糊回答

### 2. 明确性原则
- 用"我建议你选择：[选项名称]"的句式
- 避免使用"可能""或许"等模糊词汇

### 3. 不可回退原则
- 决策一旦输出，视为最终结果
- 不提供"重新分析""再次比较"等选项

### 4. 理性原则
- 当各选项优劣不明显时，允许在理性分析基础上做出果断选择
- 避免完美主义导致的决策瘫痪

## 技术栈

- **LangChain**: Agent 框架
- **LangGraph**: 工作流编排（可选）
- **OpenAI API**: LLM 接口（通过火山方舟）
- **Python 3.12**: 编程语言

## 测试状态

✅ 集成测试通过
✅ 终止规则验证通过
✅ 综合决策功能正常

## 使用场景

### 场景 1：独立使用

如果你已经有成本分析、风险评估、用户价值的分析结果，可以直接使用综合决策 Agent：

```python
# 你已经有三个维度的分析结果
cost_result = "..."
risk_result = "..."
value_result = "..."

# 使用综合决策 Agent
supervisor = SupervisorAgent()
decision = await supervisor.make_decision(
    cost_analysis=cost_result,
    risk_analysis=risk_result,
    value_analysis=value_result,
    current_round=1
)
```

### 场景 2：集成到多 Agent 系统

如果你正在构建完整的多 Agent 系统，可以将综合决策 Agent 作为最后一个节点：

```python
# 1. 调用成本分析 Agent
cost_result = await cost_agent.analyze(...)

# 2. 调用风险评估 Agent
risk_result = await risk_agent.analyze(...)

# 3. 调用用户价值 Agent
value_result = await value_agent.analyze(...)

# 4. 调用综合决策 Agent
supervisor = SupervisorAgent()
decision = await supervisor.make_decision(
    cost_analysis=cost_result,
    risk_analysis=risk_result,
    value_analysis=value_result,
    current_round=1
)
```

## 常见问题

### Q1: 如果其他 Agent 的输出格式不符合要求怎么办？

A: 综合决策 Agent 能够处理各种格式的输入，但为了获得最佳效果，建议其他 Agent 的输出包含：
- 各选项的评估结果
- 维度推荐
- 具体的评分或理由

### Q2: 如何调整终止规则的参数？

A: 修改 `config/decidex_config.json` 中的 `stopping_rules` 部分。

### Q3: 决策输出的语言是什么？

A: 当前版本使用中文。如需支持其他语言，可以修改系统提示词。

### Q4: 如何与 Arduino 硬件集成？

A: 解析最终决策中的推荐选项，将选项编号或名称发送给 Arduino：

```python
# 提取推荐的选项
option = extract_option(decision_result['final_decision'])

# 发送给 Arduino
send_to_arduino(option)
```

## 许可证

本项目为 DecideX 项目的一部分，仅用于学习和研究目的。

## 更新日志

### v1.0 (2025-01-17)
- ✅ 实现综合决策 Agent
- ✅ 实现三大终止规则
- ✅ 完成集成测试
- ✅ 移除其他 Agent，保留独立版本
