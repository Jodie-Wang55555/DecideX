"""
DecideX 决策停止规则模块（Stopping Rules）

实现 B（收敛停止）+ C（低收益停止）+ A（硬停止保底）三类规则。
判断权只属于综合 Agent（comprehensive_agent）。

B. 收敛停止：连续两轮 Top1 推荐不变，且领先优势 ≥ margin
C. 低收益停止：本轮新增观点/信息 < delta_info 阈值，或重复率过高
A. 硬停止（保底）：分析轮次 ≥ max_rounds 必须结束
"""

from dataclasses import dataclass, field
from typing import Optional


# ============================================================
# 配置参数
# ============================================================

MAX_ROUNDS = 3           # A：最大分析轮次（硬停止保底）
CONVERGENCE_MARGIN = 0.12  # B：Top1 领先 Top2 的最小分差（0~1 归一化）
MIN_NEW_POINTS = 2       # C：每轮至少需要新增的有效观点数
HIGH_REPEAT_THRESHOLD = 0.7  # C：观点重复率超过此值视为低收益


# ============================================================
# 数据结构
# ============================================================

@dataclass
class RoundResult:
    """单轮分析结果快照"""
    round_num: int
    top_recommendation: str          # 本轮 Top1 推荐方案
    confidence_scores: dict          # {"方案A": 0.85, "方案B": 0.62, ...}
    key_points: list                 # 本轮提出的关键观点列表
    controversy_count: int = 0       # 争议点数量


@dataclass
class StoppingState:
    """跨轮次的停止规则状态"""
    rounds: list = field(default_factory=list)   # List[RoundResult]
    stopped: bool = False
    stop_reason: str = ""
    stop_type: str = ""   # "A_hard" | "B_convergence" | "C_low_yield"


# ============================================================
# 停止规则评估
# ============================================================

def evaluate_stopping(state: StoppingState, current: RoundResult) -> tuple:
    """
    评估是否应该停止分析。

    Args:
        state:   历史轮次状态
        current: 当前轮次结果

    Returns:
        (should_stop: bool, reason: str, stop_type: str)
    """
    state.rounds.append(current)
    n = len(state.rounds)

    # ── A. 硬停止（保底）──────────────────────────────────────
    if n >= MAX_ROUNDS:
        return (
            True,
            f"已完成 {n} 轮分析（最大轮次 {MAX_ROUNDS}），强制输出结论。",
            "A_hard"
        )

    # 第一轮没有历史数据，不能做收敛/低收益判断
    if n < 2:
        return False, "", ""

    prev = state.rounds[-2]

    # ── B. 收敛停止 ────────────────────────────────────────────
    if current.top_recommendation == prev.top_recommendation:
        scores = current.confidence_scores
        sorted_scores = sorted(scores.values(), reverse=True)
        if len(sorted_scores) >= 2:
            lead = sorted_scores[0] - sorted_scores[1]
            if lead >= CONVERGENCE_MARGIN:
                return (
                    True,
                    (
                        f"连续两轮 Top1 均为【{current.top_recommendation}】，"
                        f"领先优势 {lead:.2f} ≥ {CONVERGENCE_MARGIN}，"
                        f"结论已收敛，停止分析。"
                    ),
                    "B_convergence"
                )

    # ── C. 低收益停止 ──────────────────────────────────────────
    prev_points = set(prev.key_points)
    curr_points = set(current.key_points)
    new_points = curr_points - prev_points
    repeat_count = len(curr_points & prev_points)
    repeat_rate = repeat_count / max(len(curr_points), 1)

    if len(new_points) < MIN_NEW_POINTS:
        return (
            True,
            (
                f"本轮仅新增 {len(new_points)} 个有效观点（阈值 {MIN_NEW_POINTS}），"
                f"继续分析收益极低，停止。"
            ),
            "C_low_yield"
        )

    if repeat_rate >= HIGH_REPEAT_THRESHOLD:
        return (
            True,
            (
                f"本轮观点重复率 {repeat_rate:.0%}（阈值 {HIGH_REPEAT_THRESHOLD:.0%}），"
                f"分析已趋于饱和，停止。"
            ),
            "C_low_yield"
        )

    return False, "", ""


# ============================================================
# 轻量版：供 Agent 工具调用的简化接口
# ============================================================

# 全局状态（单次对话生命周期内）
_stopping_state = StoppingState()


def reset_stopping_state():
    """每次新对话开始时重置状态"""
    global _stopping_state
    _stopping_state = StoppingState()


def check_should_stop(
    top_recommendation: str,
    confidence_scores: dict,
    key_points: list,
    controversy_count: int = 0,
) -> dict:
    """
    综合 Agent 调用此函数判断是否应停止分析。

    Args:
        top_recommendation: 当前轮 Top1 推荐方案名称
        confidence_scores:  各方案置信度评分，如 {"方案A": 0.85, "方案B": 0.60}
        key_points:         本轮关键观点列表，如 ["成本差异显著", "风险可控"]
        controversy_count:  当前争议点数量

    Returns:
        {
            "should_stop": bool,
            "reason": str,
            "stop_type": str,   # "A_hard" | "B_convergence" | "C_low_yield" | ""
            "round_num": int
        }
    """
    current = RoundResult(
        round_num=len(_stopping_state.rounds) + 1,
        top_recommendation=top_recommendation,
        confidence_scores=confidence_scores,
        key_points=key_points,
        controversy_count=controversy_count,
    )

    should_stop, reason, stop_type = evaluate_stopping(_stopping_state, current)

    return {
        "should_stop": should_stop,
        "reason": reason,
        "stop_type": stop_type,
        "round_num": current.round_num,
    }
