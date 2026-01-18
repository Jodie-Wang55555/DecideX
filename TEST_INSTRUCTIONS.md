# DecideX 决策系统测试说明

## 测试场景
**用户问题**："我朋友约我出去旅游，但是我有一个考试，我应该去旅游嘛"

**预期流程**：
1. 三个 Agent（成本分析、风险评估、用户价值）分别生成 4 个左右的问题
2. 用户回答这些问题
3. Supervisor Agent 给出最终决策建议

## 测试方法

### 方法1：使用 LangGraph Dev Studio（推荐）

1. **启动 Dev Studio**：
```bash
cd /Users/jodie/Documents/Langgraph-agents
uvx --refresh \
    --from "langgraph-cli[inmem]" \
    --with-editable . \
    langgraph dev
```

2. **在 Dev Studio 中**：
   - 选择 `decision-agent` graph
   - 在聊天界面输入："我朋友约我出去旅游，但是我有一个考试，我应该去旅游嘛"
   - 观察系统如何调用三个 Agent 并生成问题

### 方法2：使用 Swarm 模式测试（查看三个 Agent 独立工作）

1. **在 Dev Studio 中选择 `swarm` graph**
2. **输入同样的问题**
3. **观察三个 Agent 如何协作**

## 预期输出

### 阶段1：问题生成
- **成本分析 Agent** 应该生成关于旅行成本、时间成本、考试准备成本等问题
- **风险评估 Agent** 应该生成关于考试风险、朋友可靠性、时间冲突风险等问题  
- **用户价值 Agent** 应该生成关于个人价值观、友谊重要性、学业重要性等问题

### 阶段2：综合分析
三个 Agent 基于回答给出各自的分析结果

### 阶段3：最终决策
Supervisor Agent 汇总所有分析，给出明确的决策建议

## 注意事项

- 确保 `.env` 文件中有正确的 API 密钥
- 如果遇到模块导入错误，确保已安装依赖：`pip install -e .`
- 第一次运行可能需要一些时间来加载模型
