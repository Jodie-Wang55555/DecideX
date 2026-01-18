"""
真实测试 DecideX 决策系统 - 使用 Google Gemini API
测试场景：朋友约旅游 vs 考试
"""

import asyncio
import os
import sys
from dotenv import load_dotenv
from langchain_core.messages import HumanMessage

# 加载环境变量
load_dotenv()

# 添加 src 到路径
sys.path.insert(0, 'src')

try:
    from langchain_google_genai import ChatGoogleGenerativeAI
    USE_GOOGLE = True
except ImportError:
    from langchain_openai import ChatOpenAI
    USE_GOOGLE = False

from swarm.graph import graph as swarm_graph

async def test_real_decision():
    """真实测试决策流程"""
    
    user_question = "我朋友约我出去旅游，但是我有一个考试，我应该去旅游嘛"
    
    print("=" * 80)
    print("🤔 用户问题：")
    print(f"{user_question}\n")
    print("=" * 80)
    
    # 使用 Swarm graph 测试
    print("\n📋 测试 Swarm 模式（三个 Agent 协作）\n")
    print("-" * 80)
    
    try:
        # 调用 Swarm graph
        result = swarm_graph.invoke({
            "messages": [HumanMessage(content=user_question)]
        })
        
        # 获取最后一条消息
        if "messages" in result:
            last_message = result["messages"][-1]
            response = last_message.content if hasattr(last_message, "content") else str(last_message)
        else:
            response = str(result)
        
        print("✅ Swarm 系统响应：\n")
        print(response)
        print("\n" + "-" * 80)
        
    except Exception as e:
        print(f"❌ 错误: {str(e)[:300]}")
        import traceback
        traceback.print_exc()
    
    print("\n" + "=" * 80)
    print("✅ 测试完成！")
    print("=" * 80)

if __name__ == "__main__":
    asyncio.run(test_real_decision())
