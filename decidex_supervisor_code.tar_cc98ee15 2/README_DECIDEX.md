# DecideX 多 Agent 决策系统

## 项目简介

DecideX 是一个面向"选择困难症"的软硬件结合智能决策辅助系统。本项目实现了其核心的软件部分——多 Agent 决策系统。

### 核心理念

DecideX 的理念是将决策从"脑内反复权衡"转移到"系统 + 物理执行"：
- 用户输入决策问题和选项
- Agent 在后台完成决策分析与终止判断
- 最终结果通过物理方式呈现（如转盘、灯泡等），用户只能"接受并执行"

### 系统架构

DecideX 采用 **Supervisor 模式**的多 Agent 协作架构：

```
用户输入 → 成本分析 Agent → 风险评估 Agent → 用户价值 Agent → 综合决策 Agent → 最终决策
```

#### Agent 角色分工

1. **成本分析 Agent**
   - 评估时间、金钱、资源成本
   - 识别机会成本
   - 给出成本维度的推荐

2. **风险评估 Agent**
   - 识别不确定性因素
   - 评估失败概率和后果
   - 分析可逆性
   - 给出风险维度的推荐

3. **用户价值 Agent**
   - 评估与用户价值观的匹配度
   - 分析成就导向、安全感、自主性等维度
   - 给出价值维度的推荐

4. **综合决策 Agent**
   - 汇总三个维度的分析结果
   - 判断何时停止分析（终止规则）
   - 给出唯一、明确、不可回退的最终决策

#### 终止规则

系统采用三种终止规则来判断何时应该停止分析：

1. **硬停止规则**（必须执行）
   - 最大轮次限制：最多 2 轮分析
   - 时间限制：单次分析超过 30 秒强制停止

2. **收敛停止规则**（推荐执行）
   - 评分收敛：Top1 选项连续两轮保持不变，且领先优势 ≥ 0.12
   - 观点趋同：争议点数量 ≤ 1 个

3. **低收益停止规则**（谨慎执行）
   - 新信息增量 < 0.2（按 0~1 归一化）
   - 重复率 ≥ 0.8

## 项目结构

```
.
├── config/
│   ├── agent_llm_config.json      # Agent LLM 配置（用户价值观 Agent）
│   └── decidex_config.json        # DecideX 系统配置
├── src/
│   ├── agents/
│   │   ├── agent.py               # 用户价值观 Agent（已有）
│   │   ├── cost_agent.py          # 成本分析 Agent（用户已实现）
│   │   ├── risk_agent.py          # 风险评估 Agent（用户已实现）
│   │   ├── value_agent.py         # 用户价值 Agent（用户已实现）
│   │   └── supervisor_agent.py    # 综合决策 Agent（新增）
│   └── graphs/
│       └── decidex_graph.py       # DecideX 工作流（新增）
├── tests/
│   ├── test_decidex_workflow.py   # 完整工作流测试
│   └── test_decidex_quick.py      # 快速测试（推荐）
├── examples/
│   └── decidex_example.py         # 使用示例
└── README_DECIDEX.md              # 本文档
```

## 快速开始

### 1. 运行快速测试

```bash
python tests/test_decidex_quick.py
```

测试内容包括：
- 终止规则验证
- 综合决策 Agent 功能

### 2. 运行完整测试

```bash
python tests/test_decidex_workflow.py
```

测试整个多 Agent 协作流程（可能需要 1-2 分钟）。

### 3. 运行使用示例

```bash
python examples/decidex_example.py
```

交互式运行示例，了解如何使用 DecideX 系统。

## 核心功能

### 综合决策 Agent

综合决策 Agent 是整个系统的核心，位于 `src/agents/supervisor_agent.py`。

**主要功能：**
1. **结果汇总**：整合成本、风险、用户价值三个维度的分析结果
2. **终止判断**：运用三大终止规则判断何时结束分析
3. **综合决策**：在信息充足时做出明确决策，在信息不足时给出"合理假设下的最优选择"
4. **决策表达**：用清晰、有力、不可回退的语气表达决策结果

**使用方法：**

```python
from src.agents.supervisor_agent import SupervisorAgent

# 创建综合决策 Agent
supervisor = SupervisorAgent()

# 做出决策
decision_result = await supervisor.make_decision(
    cost_analysis="成本分析结果...",
    risk_analysis="风险评估结果...",
    value_analysis="用户价值分析结果...",
    current_round=1
)

# 获取决策
print(decision_result['final_decision'])
print(f"是否应该停止：{decision_result['should_stop']}")
print(f"停止原因：{decision_result['stop_reason']}")
```

### DecideX 工作流

DecideX 工作流编排了所有 Agent 的执行顺序，位于 `src/graphs/decidex_graph.py`。

**执行流程：**
1. 用户输入决策问题和选项
2. 成本分析 Agent 分析成本维度
3. 风险评估 Agent 分析风险维度
4. 用户价值 Agent 分析价值维度
5. 综合决策 Agent 汇总分析并判断是否终止
6. 如果不终止，回到步骤 2 进行新一轮分析
7. 如果终止，输出最终决策

**使用方法：**

```python
from src.graphs.decidex_graph import DecideXWorkflow

# 创建工作流
workflow = DecideXWorkflow()

# 运行决策
result = await workflow.run(
    user_query="我在当前公司工作了3年...",
    options=["跳槽到新公司", "留在原公司", "继续观望"]
)

# 获取结果
print(result['cost_analysis'])
print(result['risk_analysis'])
print(result['value_analysis'])
print(result['final_decision'])
```

## 配置说明

### DecideX 配置文件

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

## 技术栈

- **LangChain**: Agent 框架
- **LangGraph**: 工作流编排
- **OpenAI API**: LLM 接口（通过火山方舟）
- **Python 3.12**: 编程语言

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

## 后续扩展

### 与 Arduino 硬件集成

DecideX 的最终决策需要通过物理方式呈现，例如：
- 老虎机：旋转后指向被选中的选项
- 转盘：停在某一选项上
- 灯泡：对应的选项灯泡亮起

硬件接口示例（伪代码）：

```python
# 将决策结果发送到 Arduino
def send_to_arduino(decision: str):
    # 提取选项编号
    option_index = extract_option_index(decision)

    # 通过串口发送指令
    serial_port.write(f"EXECUTE:{option_index}\n")

    # Arduino 驱动物理执行装置
    # - 控制转盘旋转
    # - 控制灯泡亮起
    # - 控制老虎机
```

### 用户反馈收集

在决策执行完成后，可以收集用户反馈：
- 决策是否满意？
- 执行过程中遇到什么问题？
- 需要调整哪些分析维度？

反馈不会影响当前已完成的决策，仅用于长期行为建模与系统优化。

## 常见问题

### Q1: 为什么不用投票或平均分？

A: DecideX 的目标是"结束决策"，而非"民主投票"。投票和平均会鼓励继续比较，而不是终止。选择困难症患者的问题不是缺少信息，而是无法停止分析。

### Q2: 如果 Agent 也犹豫怎么办？

A: 系统不追求"绝对最优"，只追求"足够合理 + 必须结束"。当区分度不够时，允许随机 + 物理执行。

### Q3: 为什么一定要接物理硬件？

A: 物理执行不是展示，而是心理上的"不可逆信号"。它让用户从"思考者"变成"执行者"，符合选择困难症患者的问题。

### Q4: 这个项目解决的是什么？

A: DecideX 解决的是"我该选什么"和"我什么时候应该停止想"。在人已经具备足够理性信息的前提下，帮助用户判断何时应该停止分析，并进入执行阶段。

## 测试状态

✅ 终止规则测试通过
✅ 综合决策 Agent 测试通过
⏳ 完整工作流测试（由于涉及多个 LLM 调用，需要较长时间）

## 参考资源

- [LangGraph Agents](https://github.com/pareshraut/Langgraph-agents) - Supervisor 模式参考
- [ChoiceMates](https://arxiv.org/abs/2310.01331) - 多智能体对话系统研究
- [PromethAI](https://github.com/topoteretes/PromethAI-Backend) - 决策辅助 Agent 参考

## 许可证

本项目为 DecideX 项目的一部分，仅用于学习和研究目的。
