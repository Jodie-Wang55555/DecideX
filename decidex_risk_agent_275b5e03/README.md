# DecideX 风险评估 Agent

## 概述
DecideX 风险评估 Agent 是智能决策辅助系统的核心模块，专注于识别决策方案的不确定性因素和评估失败后果。

## 功能特性

### 1. 动态选择题生成
- 根据用户具体决策场景动态生成前置条件选择题（非固定模板）
- 输出纯 JSON 格式，便于前端解析
- 自动识别决策场景中的关键对象（朋友、同事、家人等）
- 涉及对象时强制包含对象相关问题（至少2个）

### 2. 完整风险评估流程
- 不确定性因素识别（内部/外部/不可控因素）
- 失败后果评估（直接/间接后果、连锁效应）
- 风险概率预测（高频低影响、低频高影响、黑天鹅事件）
- 风险影响分析（对核心目标、连锁效应、持续性）
- 风险等级评定（高/中/低）
- 风险应对建议（规避、减轻、转移、接受）

## 快速开始

### 安装依赖
```bash
pip install -r requirements.txt
```

### 配置说明
编辑 `config/agent_llm_config.json`，配置模型参数：
- `model`: 使用的模型（默认：doubao-seed-1-8-251228）
- `temperature`: 温度参数（默认：0.3）
- 其他模型参数...

### 运行 Agent
```python
from src.agents.agent import build_agent

# 构建 Agent
agent = build_agent()

# 使用 Agent
result = agent.invoke({"messages": [("user", "帮我评估和朋友创业的风险")]})
```

## 前端集成

### JSON 输出示例
```json
{
  "type": "precondition_questions",
  "message": "为了给你提供精准的风险评估，请快速选择以下问题",
  "questions": [
    {
      "id": 1,
      "question": "你和朋友的核心能力匹配度如何？",
      "options": [
        {"key": "A", "label": "高度互补"},
        {"key": "B", "label": "部分重叠"},
        {"key": "C", "label": "完全一致"}
      ]
    }
  ]
}
```

### 前端解析代码
```javascript
try {
  const data = JSON.parse(response);
  // 渲染选择题界面
  data.questions.forEach(q => {
    // 处理每个问题
  });
} catch (e) {
  // 错误处理
}
```

## 支持的决策场景

1. **投资理财**：风险承受能力、风险偏好、资金来源、失败影响
2. **职业选择**：工作稳定性、失败后果、风险承受能力、备选方案
3. **创业项目**：市场不确定性、团队可靠性、资金链风险、失败后果
4. **合作场景**：对象可靠性、责任能力、风险偏好、配合度（强制包含对象问题）
5. **其他决策**：自动识别场景并生成针对性问题

## 技术栈
- Python 3.8+
- LangChain 1.0+
- LangGraph 1.0+
- doubao-seed-1-8-251228 (大语言模型)

## 注意事项
1. 首次运行会生成前置条件选择题（JSON 格式）
2. 用户回答后，再次调用获取完整风险评估报告
3. 风险评估报告为 Markdown 格式
4. 保证输入决策场景清晰，以便生成准确的问题

## 许可证
MIT License
