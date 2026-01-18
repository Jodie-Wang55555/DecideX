import os
import json
from typing import TypedDict, Annotated
from langchain_openai import ChatOpenAI
from langchain_core.messages import AnyMessage, HumanMessage, AIMessage
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from coze_coding_utils.runtime_ctx.context import default_headers
from storage.memory.memory_saver import get_memory_saver

CONFIG_PATH = "config/decidex_config.json"


class DecisionState(TypedDict):
    """决策状态管理"""
    messages: Annotated[list[AnyMessage], add_messages]
    current_round: int
    agent_results: dict[str, str]
    cost_analysis: str
    risk_analysis: str
    value_analysis: str
    final_decision: str
    should_stop: bool


class SupervisorAgent:
    """
    DecideX 综合决策 Agent

    职责：
    1. 汇总成本、风险、用户价值三个分析 Agent 的结果
    2. 判断是否应该停止分析（终止规则）
    3. 给出最终决策建议

    终止规则：
    - 硬停止：最多 2 轮分析
    - 收敛停止：各 Agent 结论高度一致（领先优势 ≥ 0.12）
    - 低收益停止：新增信息很少（相似度 ≥ 0.8）
    """

    def __init__(self):
        self.config = self._load_config()
        self.llm = self._create_llm()

    def _load_config(self) -> dict:
        """加载配置文件"""
        workspace_path = os.getenv("COZE_WORKSPACE_PATH", "/workspace/projects")
        config_path = os.path.join(workspace_path, CONFIG_PATH)

        with open(config_path, 'r', encoding='utf-8') as f:
            return json.load(f)

    def _create_llm(self):
        """创建 LLM 实例"""
        api_key = os.getenv("COZE_WORKLOAD_IDENTITY_API_KEY")
        base_url = os.getenv("COZE_INTEGRATION_MODEL_BASE_URL")

        return ChatOpenAI(
            model=self.config.get("model", "doubao-seed-1-8-251228"),
            api_key=api_key,
            base_url=base_url,
            temperature=self.config.get("temperature", 0.3),
            streaming=True,
            timeout=self.config.get("timeout", 600),
            extra_body={
                "thinking": {
                    "type": self.config.get("thinking", "disabled")
                }
            }
        )

    def get_system_prompt(self) -> str:
        """获取综合决策 Agent 的系统提示词"""
        return """# 角色定义
你是 DecideX 系统中的综合决策专家代理，是决策分析流程的最终决策者。你负责汇总成本分析、风险评估、用户价值三个维度的分析结果，运用科学的方法论进行综合研判，并在满足终止条件时给出唯一、明确、不可回退的最终决策建议。

# 任务目标
你的核心任务是基于多维分析结果，运用终止规则判断何时停止分析，并给出一个清晰明确的最终决策，帮助用户摆脱"选择困难症"，从"思考者"转变为"执行者"。

# 能力
- **结果汇总能力**：整合成本、风险、用户价值三个维度的分析结果
- **终止判断能力**：运用硬停止、收敛停止、低收益停止三大终止规则判断何时结束分析
- **综合决策能力**：在信息充足时做出明确决策，在信息不足时给出"合理假设下的最优选择"
- **决策表达能力**：用清晰、有力、不可回退的语气表达决策结果

# 终止规则（严格遵循）
## 1. 硬停止规则（必须执行）
- **最大轮次限制**：分析轮次达到 2 轮时，必须停止分析并给出决策
- **时间限制**：单次分析耗时超过 30 秒时，强制停止
- **原因**：防止分析陷入无休止的权衡，从机制上限制过度思考

## 2. 收敛停止规则（推荐执行）
- **评分收敛**：当多个 Agent 给出的排序中，Top1 选项连续两轮保持不变，且领先优势 ≥ 0.12（按 0~1 归一化分）时，认为决策已趋于稳定
- **观点趋同**：当争议点数量下降到阈值（如 ≤ 1 个）或"重大风险"已被解决/接受时，可以停止
- **原因**：当分析结果稳定时，继续分析边际收益很低

## 3. 低收益停止规则（谨慎执行）
- **新信息增量小**：当新一轮分析提出的新证据/新维度 < 0.2（按 0~1 归一化）时，认为继续分析价值不大
- **重复率高**：当本轮论点与上一轮相似度 ≥ 0.8 时，建议停止
- **原因**：避免在已充分讨论的维度上反复纠结

# 决策输出原则
1. **唯一性原则**：只能给出一个最终决策，不能给出"建议 A 和 B 都可以考虑"的模糊回答
2. **明确性原则**：用"我建议你选择：[选项名称]"的句式，避免使用"可能""或许"等模糊词汇
3. **不可回退原则**：决策一旦输出，视为最终结果，不提供"重新分析""再次比较"等选项
4. **理性原则**：当各选项优劣不明显时，允许在理性分析基础上做出果断选择，而非逃避决策
5. **理由支撑原则**：必须用 1-3 句简明扼要的理由支撑决策，但理由不能成为继续犹豫的理由

# 工作流程
1. **分析汇总**
   - 读取成本分析 Agent 的结果：关注时间、金钱、资源成本
   - 读取风险评估 Agent 的结果：关注不确定性、失败后果
   - 读取用户价值 Agent 的结果：关注与用户价值观的匹配度

2. **终止判断**
   - 检查是否达到最大轮次限制（硬停止）
   - 检查分析结果是否收敛（收敛停止）
   - 检查新增信息量是否充足（低收益停止）
   - 如果任一终止条件满足，进入决策输出阶段

3. **综合权衡**
   - 识别各选项在三个维度上的优劣势
   - 识别选项之间的权衡关系
   - 识别可能的决策后悔点和执行难点

4. **决策输出**
   - 选择综合得分最高的选项（或避免最大风险的选项）
   - 用明确的语言陈述决策
   - 用简明的理由支撑决策
   - 禁止提供"重新选择"的选项

# 输出格式

## 综合分析摘要（Markdown 格式）
### 📊 多维分析汇总
**成本维度分析**：
[汇总成本分析结果，用 2-3 句话概括]

**风险维度分析**：
[汇总风险评估结果，用 2-3 句话概括]

**用户价值维度分析**：
[汇总用户价值分析结果，用 2-3 句话概括]

### 🎯 终止判断
**当前轮次**：第 X 轮 / 最大 2 轮
**判断结果**：[满足/不满足] 终止条件
**终止原因**：[如果满足终止条件，说明具体原因]

### ✅ 最终决策建议
**我建议你选择：[选项名称]**

**理由**：
1. [理由1]
2. [理由2]
3. [理由3]

**行动建议**：
[1-2 句话关于如何执行这个决策的具体建议]

---

## 说明
- 本决策基于成本、风险、用户价值三个维度的综合分析
- 决策已做出，建议你接受并执行，而非继续比较
- 如果执行后发现问题，可以作为下次决策的经验

# 约束
- **必须给出决策**：即使信息不完美，也必须做出选择，不能说"信息不足，无法决策"
- **只能给出一个选择**：不能给出"可以考虑 A 或 B"的模糊建议
- **禁止回退选项**：不能说"如果你不满意，可以重新分析"
- **理性但果断**：在理性分析基础上，做出果断决策，避免完美主义
- **语言清晰有力**：用肯定的语气，避免使用"可能""或许""建议考虑"等模糊词汇

# 错误处理
- 当某个 Agent 的结果缺失时，基于已有信息做出决策，并说明缺失维度的影响
- 当多个 Agent 的结论严重冲突时，优先考虑风险维度，避免高风险选项
- 当所有选项优劣势接近时，基于用户价值维度做出选择
"""

    def should_stop_analysis(
        self,
        current_round: int,
        previous_results: dict[str, str] | None,
        current_results: dict[str, str]
    ) -> tuple[bool, str]:
        """
        判断是否应该停止分析

        Args:
            current_round: 当前轮次
            previous_results: 上一轮的分析结果
            current_results: 当前轮的分析结果

        Returns:
            (should_stop, reason): 是否应该停止以及原因
        """
        stopping_rules = self.config.get("stopping_rules", {})
        max_rounds = stopping_rules.get("max_rounds", 2)

        # 1. 硬停止：检查最大轮次
        if current_round >= max_rounds:
            return True, f"已达到最大分析轮次 {max_rounds}，必须给出最终决策"

        # 2. 收敛停止：检查结果稳定性（简化版）
        if previous_results is not None:
            # 检查各 Agent 的推荐选项是否一致
            convergence_margin = stopping_rules.get("convergence_margin", 0.12)

            # 如果结果高度相似，可以停止
            if self._check_results_convergence(
                previous_results,
                current_results,
                convergence_margin
            ):
                return True, "各维度分析结果已趋于稳定，继续分析边际收益低"

        # 3. 低收益停止：检查信息增量（简化版）
        if previous_results is not None:
            min_new_info = stopping_rules.get("min_new_info_threshold", 0.2)

            if self._check_info_gain(
                previous_results,
                current_results,
                min_new_info
            ):
                return False, "仍有新信息产生，继续分析可能有益"

            return True, "本轮新增信息量不足，建议终止分析"

        # 如果是第一轮，继续分析
        return False, "第一轮分析完成，需要更多信息支持决策"

    def _check_results_convergence(
        self,
        prev: dict[str, str],
        curr: dict[str, str],
        margin: float
    ) -> bool:
        """
        检查结果是否收敛

        简化版实现：检查文本相似度
        实际项目中可以使用更复杂的评分系统
        """
        # 这里使用简单的文本匹配作为示例
        # 实际应该提取推荐的选项名称进行比较
        for key in prev.keys():
            if key not in curr:
                return False

            # 如果结果差异较大，认为未收敛
            if not self._is_similar(prev[key], curr[key], 0.8):
                return False

        return True

    def _check_info_gain(
        self,
        prev: dict[str, str],
        curr: dict[str, str],
        threshold: float
    ) -> bool:
        """
        检查是否有足够的新信息

        返回 True 表示有足够新信息，应该继续分析
        """
        # 简化版实现：检查文本差异性
        total_diff = 0
        for key in prev.keys():
            if key in curr:
                similarity = self._calculate_similarity(prev[key], curr[key])
                total_diff += (1 - similarity)

        avg_diff = total_diff / len(prev) if prev else 0
        return avg_diff >= threshold

    def _is_similar(self, text1: str, text2: str, threshold: float) -> bool:
        """检查两段文本是否相似"""
        similarity = self._calculate_similarity(text1, text2)
        return similarity >= threshold

    def _calculate_similarity(self, text1: str, text2: str) -> float:
        """
        计算两段文本的相似度（简化版）

        返回 0~1 之间的值，1 表示完全相同
        """
        # 简化版：基于词重合度计算相似度
        # 实际项目中可以使用更高级的文本相似度算法
        words1 = set(text1.lower().split())
        words2 = set(text2.lower().split())

        if not words1 and not words2:
            return 1.0

        intersection = words1.intersection(words2)
        union = words1.union(words2)

        if not union:
            return 1.0

        return len(intersection) / len(union)

    async def make_decision(
        self,
        cost_analysis: str,
        risk_analysis: str,
        value_analysis: str,
        current_round: int,
        previous_results: dict[str, str] | None = None
    ) -> dict:
        """
        做出最终决策

        Args:
            cost_analysis: 成本分析结果
            risk_analysis: 风险评估结果
            value_analysis: 用户价值分析结果
            current_round: 当前轮次
            previous_results: 上一轮的分析结果

        Returns:
            dict: 包含决策结果和终止判断的字典
        """
        # 1. 判断是否应该停止分析
        should_stop, stop_reason = self.should_stop_analysis(
            current_round,
            previous_results,
            {
                "cost": cost_analysis,
                "risk": risk_analysis,
                "value": value_analysis
            }
        )

        # 2. 构建提示词
        system_prompt = self.get_system_prompt()

        user_message = f"""请基于以下三个维度的分析结果，做出最终决策：

## 成本分析结果：
{cost_analysis}

## 风险评估结果：
{risk_analysis}

## 用户价值分析结果：
{value_analysis}

## 当前状态：
- 当前轮次：第 {current_round} 轮
- 终止判断：{stop_reason}
- 是否应该停止：{'是' if should_stop else '否'}

请按照输出格式给出综合分析和最终决策建议。"""

        # 3. 调用 LLM 生成决策
        messages = [
            HumanMessage(content=user_message)
        ]

        response = await self.llm.ainvoke(messages)

        # 4. 返回结果
        return {
            "should_stop": should_stop,
            "stop_reason": stop_reason,
            "current_round": current_round,
            "cost_analysis": cost_analysis,
            "risk_analysis": risk_analysis,
            "value_analysis": value_analysis,
            "final_decision": response.content,
            "agent_results": {
                "cost": cost_analysis,
                "risk": risk_analysis,
                "value": value_analysis
            }
        }


def create_supervisor_agent() -> SupervisorAgent:
    """创建综合决策 Agent 实例"""
    return SupervisorAgent()
