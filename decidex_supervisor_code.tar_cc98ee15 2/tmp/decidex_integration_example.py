"""
DecideX 成本分析 Agent 集成示例
展示如何在您的项目中使用成本分析 Agent
"""

import asyncio
import os
import sys
from typing import Optional, Dict, Any

# ===== 方式一：添加路径后 import =====
def setup_decidex_path(decidex_root: str):
    """
    将 DecideX 代码目录添加到 Python 路径

    Args:
        decidex_root: DecideX 代码的根目录路径
    """
    if decidex_root not in sys.path:
        sys.path.insert(0, decidex_root)


# ===== 使用示例 =====
async def example_1_basic_usage():
    """
    示例 1: 基础使用
    """
    print("\n=== 示例 1: 基础使用 ===")

    # 设置 DecideX 路径（修改为实际路径）
    decidex_root = "/path/to/decidex-agent"
    setup_decidex_path(decidex_root)

    # import 并创建 Agent
    from agents.agent import build_agent

    agent = build_agent()

    # 调用 Agent
    result = await agent.ainvoke({
        "messages": [{"role": "user", "content": "我想和朋友去旅行，帮我分析成本"}]
    })

    print(f"结果: {result}")


# ===== 封装为服务类 =====
class CostAnalysisService:
    """
    成本分析服务类
    封装 DecideX Agent 的调用逻辑
    """

    def __init__(self, decidex_root: str):
        """
        初始化服务

        Args:
            decidex_root: DecideX 代码的根目录路径
        """
        setup_decidex_path(decidex_root)
        self._agent = None

    def _get_agent(self):
        """延迟加载 Agent"""
        if self._agent is None:
            from agents.agent import build_agent
            self._agent = build_agent()
        return self._agent

    async def analyze_cost(self, user_input: str, session_id: str = None) -> Dict[str, Any]:
        """
        分析成本

        Args:
            user_input: 用户输入的决策场景
            session_id: 会话ID（用于多轮对话）

        Returns:
            分析结果
        """
        agent = self._get_agent()

        config = {}
        if session_id:
            config["configurable"] = {"thread_id": session_id}

        result = await agent.ainvoke(
            {"messages": [{"role": "user", "content": user_input}]},
            config=config
        )

        return result


# ===== 主函数 =====
async def main():
    """运行示例"""
    print("DecideX 成本分析 Agent 集成示例")
    print("=" * 50)

    # 运行示例（请先修改 decidex_root 路径）
    try:
        # await example_1_basic_usage()
        pass
    except Exception as e:
        print(f"\n⚠️  请先修改示例中的 decidex_root 路径为您实际的 DecideX 代码目录")
        print(f"错误信息: {e}")
        print("\n使用步骤:")
        print("1. 下载并解压 decidex_agent.tar.gz")
        print("2. 修改示例中的 decidex_root 为解压后的目录路径")
        print("3. 运行此脚本: python integration_example.py")


if __name__ == "__main__":
    asyncio.run(main())
