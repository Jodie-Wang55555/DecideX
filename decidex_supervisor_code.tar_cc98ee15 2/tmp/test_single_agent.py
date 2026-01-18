"""
测试用户价值观 Agent
"""
import asyncio
import sys

# 添加项目路径
sys.path.insert(0, '/workspace/projects')
sys.path.insert(0, '/workspace/projects/src')

from agents.agent import build_agent

async def test_agent():
    """测试用户价值观 Agent"""
    print("=" * 60)
    print("测试用户价值观 Agent")
    print("=" * 60)

    # 构建 Agent
    print("\n1. 构建 Agent...")
    agent = build_agent()
    print("✅ Agent 构建成功")

    # 测试场景：价值观分析
    print("\n" + "=" * 60)
    print("测试场景：职业选择价值观分析")
    print("=" * 60)
    print("用户输入：我觉得追求成功和成就感对我来说很重要，但同时我也很看重生活的稳定性")
    print("-" * 60)

    try:
        result = await agent.ainvoke({
            "messages": [{"role": "user", "content": "我觉得追求成功和成就感对我来说很重要，但同时我也很看重生活的稳定性"}]
        }, config={"configurable": {"thread_id": "test_session"}})

        # 打印结果
        print("\nAgent 响应：")
        if "messages" in result and result["messages"]:
            last_message = result["messages"][-1]
            content = last_message.content if hasattr(last_message, 'content') else str(last_message)
            print(content)
        else:
            print("No messages in result")

        print("\n✅ 测试通过！")

    except Exception as e:
        print(f"\n❌ 测试失败：{e}")
        import traceback
        traceback.print_exc()

    print("\n" + "=" * 60)
    print("测试完成")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(test_agent())
