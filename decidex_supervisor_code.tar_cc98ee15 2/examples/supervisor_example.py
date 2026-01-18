"""
综合决策 Agent 使用示例

这个示例展示如何独立使用综合决策 Agent。
"""

import asyncio
import sys
import os

# 添加项目路径
project_root = os.path.join(os.path.dirname(__file__), '..')
sys.path.insert(0, project_root)
src_path = os.path.join(project_root, 'src')
if src_path not in sys.path:
    sys.path.insert(0, src_path)


async def example_simple_usage():
    """简单使用示例"""
    print("\n" + "="*80)
    print("📋 示例 1: 简单使用")
    print("="*80)

    from src.agents.supervisor_agent import SupervisorAgent

    # 创建综合决策 Agent
    supervisor = SupervisorAgent()

    # 输入数据（来自其他 Agent）
    cost_analysis = """
    ## 💰 成本分析

    **选项 A: 买房**
    - 时间成本：需要 1-3 个月找房、签合同
    - 金钱成本：首付 150 万，月供 8000 元
    - 资源成本：大量现金流被锁定
    - 机会成本：失去其他投资机会
    - **综合成本评分**：8/10

    **选项 B: 继续租房**
    - 时间成本：无需额外时间
    - 金钱成本：月租 5000 元
    - 资源成本：现金流灵活
    - 机会成本：失去房产增值
    - **综合成本评分**：4/10

    **成本维度推荐**：继续租房（成本更低）
    """

    risk_analysis = """
    ## ⚠️ 风险评估

    **选项 A: 买房**
    - 不确定性：房价波动、利率变化
    - 最坏情况：房价下跌 30%
    - 失败概率：中等（35%）
    - 可逆性：不可逆
    - **综合风险评分**：7/10

    **选项 B: 继续租房**
    - 不确定性：房东涨价
    - 最坏情况：租金大幅上涨
    - 失败概率：低（20%）
    - 可逆性：可逆
    - **综合风险评分**：4/10

    **风险维度推荐**：继续租房（风险更低）
    """

    value_analysis = """
    ## 💎 价值匹配分析

    **选项 A: 买房**
    - 成就导向：8/10，拥有自己的房子
    - 安全感：9/10，稳定的居住环境
    - 自主性：7/10，可以自由装修
    - **综合价值评分**：8/10

    **选项 B: 继续租房**
    - 成就导向：4/10，缺乏归属感
    - 安全感：5/10，随时可能搬家
    - 自主性：5/10，受房东限制
    - **综合价值评分**：5/10

    **价值维度推荐**：买房（更符合安全感价值观）
    """

    print(f"\n📊 输入数据：")
    print(f"  - 成本分析：买房成本高，租房成本低")
    print(f"  - 风险评估：买房风险高，租房风险低")
    print(f"  - 用户价值：买房更符合价值观")

    print(f"\n⏳ 正在综合分析并给出决策...")

    # 使用综合决策 Agent
    decision_result = await supervisor.make_decision(
        cost_analysis=cost_analysis,
        risk_analysis=risk_analysis,
        value_analysis=value_analysis,
        current_round=1
    )

    # 输出结果
    print(f"\n" + "="*80)
    print("✅ 决策结果")
    print("="*80)
    print(decision_result['final_decision'])

    print(f"\n📋 决策信息：")
    print(f"  - 应该停止：{decision_result['should_stop']}")
    print(f"  - 停止原因：{decision_result['stop_reason']}")
    print(f"  - 当前轮次：{decision_result['current_round']}")

    return decision_result


async def example_termination_check():
    """终止判断示例"""
    print("\n" + "="*80)
    print("📋 示例 2: 终止判断")
    print("="*80)

    from src.agents.supervisor_agent import SupervisorAgent

    supervisor = SupervisorAgent()

    # 第一轮分析
    print(f"\n🔍 第一轮分析：")
    should_stop, reason = supervisor.should_stop_analysis(
        current_round=1,
        previous_results=None,
        current_results={
            "cost": "选项A成本较低，选项B成本较高",
            "risk": "选项A风险低，选项B风险高",
            "value": "选项A更符合价值观"
        }
    )

    print(f"  是否应该停止：{should_stop}")
    print(f"  原因：{reason}")

    # 第二轮分析（达到最大轮次）
    print(f"\n🔍 第二轮分析（达到最大轮次）：")
    should_stop, reason = supervisor.should_stop_analysis(
        current_round=2,
        previous_results={
            "cost": "选项A成本较低，选项B成本较高",
            "risk": "选项A风险低，选项B风险高",
            "value": "选项A更符合价值观"
        },
        current_results={
            "cost": "选项A成本较低，选项B成本较高",
            "risk": "选项A风险低，选项B风险高",
            "value": "选项A更符合价值观"
        }
    )

    print(f"  是否应该停止：{should_stop}")
    print(f"  原因：{reason}")


async def main():
    """运行所有示例"""
    print("\n" + "="*80)
    print("🚀 综合决策 Agent 使用示例")
    print("="*80)

    # 示例 1: 简单使用
    await example_simple_usage()

    # 示例 2: 终止判断
    await example_termination_check()

    print("\n" + "="*80)
    print("✅ 示例运行完成")
    print("="*80)

    print("\n📚 更多信息：")
    print("  - 文档：README_SUPERVISOR.md")
    print("  - 测试：tests/test_supervisor_integration.py")
    print("  - 配置：config/decidex_config.json")


if __name__ == "__main__":
    asyncio.run(main())
