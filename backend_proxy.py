"""
DecideX 前端后端代理服务
连接前端和 LangGraph 后端 API
"""
try:
    from fastapi import FastAPI, HTTPException, UploadFile, File, Form
    from fastapi.middleware.cors import CORSMiddleware
    from pydantic import BaseModel
    from typing import Optional
    import httpx
    import os
    HAS_FASTAPI = True
except ImportError:
    HAS_FASTAPI = False
    print("警告: 未安装 FastAPI，请运行: pip install fastapi uvicorn")

if HAS_FASTAPI:
    app = FastAPI(title="DecideX Backend Proxy")

    # 配置 CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:8000", "http://127.0.0.1:8000", "*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # LangGraph Dev Studio 默认地址
    LANGRAPH_BASE_URL = os.getenv("LANGRAPH_BASE_URL", "http://localhost:8123")

    # 智能体映射到 langgraph.json 中定义的 graph
    AGENT_MAP = {
        "decision": "decision-agent"
    }

    class ChatRequest(BaseModel):
        agent: str
        message: str
        conversation_id: Optional[str] = None

    class ChatResponse(BaseModel):
        response: str
        conversation_id: Optional[str] = None

    @app.get("/")
    async def root():
        return {
            "status": "running",
            "langgraph_url": LANGRAPH_BASE_URL,
            "message": "DecideX Backend Proxy Service",
            "available_agents": list(AGENT_MAP.keys())
        }

    @app.post("/chat", response_model=ChatResponse)
    async def chat(request: ChatRequest):
        """
        处理聊天请求，转发到 LangGraph 后端
        """
        try:
            # 映射前端智能体名称到 LangGraph graph 名称
            graph_name = AGENT_MAP.get(request.agent, "decision-agent")
            
            # 使用线程ID（会话ID）
            thread_id = request.conversation_id or f"thread_{graph_name}_{hash(request.message) % 10000}"
            
            # LangGraph API 端点格式
            # LangGraph Dev Studio 使用 /threads/{thread_id}/runs 端点
            api_url = f"{LANGRAPH_BASE_URL}/threads/{thread_id}/runs"
            
            # 构建请求体 - LangGraph API 格式
            payload = {
                "assistant_id": graph_name,
                "input": {
                    "messages": [
                        {
                            "role": "user",
                            "content": request.message
                        }
                    ]
                },
                "stream": False
            }
            
            async with httpx.AsyncClient(timeout=120.0) as client:
                try:
                    # 调用 LangGraph API
                    response = await client.post(api_url, json=payload)
                    
                    if response.status_code == 200:
                        data = response.json()
                        
                        # 解析 LangGraph 响应
                        # 响应格式可能是: {"output": {...}, "run_id": "..."}
                        output = data.get("output", {})
                        
                        # 尝试提取消息内容
                        if isinstance(output, dict):
                            # 如果 output 包含 messages
                            if "messages" in output:
                                messages = output["messages"]
                                # 查找最后一条助手消息
                                for msg in reversed(messages):
                                    if isinstance(msg, dict) and msg.get("role") == "assistant":
                                        content = msg.get("content", "")
                                        if isinstance(content, str):
                                            return ChatResponse(
                                                response=content,
                                                conversation_id=thread_id
                                            )
                                        elif isinstance(content, list):
                                            # 处理内容列表
                                            text_parts = []
                                            for item in content:
                                                if isinstance(item, dict):
                                                    text_parts.append(item.get("text", ""))
                                                elif isinstance(item, str):
                                                    text_parts.append(item)
                                            return ChatResponse(
                                                response=" ".join(text_parts),
                                                conversation_id=thread_id
                                            )
                            
                            # 如果 output 直接包含文本
                            if "text" in output:
                                return ChatResponse(
                                    response=output["text"],
                                    conversation_id=thread_id
                                )
                        
                        # 如果无法解析，返回原始输出
                        return ChatResponse(
                            response=str(output) if output else "已收到您的消息",
                            conversation_id=thread_id
                        )
                    else:
                        error_text = response.text
                        return ChatResponse(
                            response=f"后端返回错误 (状态码: {response.status_code}): {error_text}\n\n请确保 LangGraph Dev Studio 正在运行。",
                            conversation_id=thread_id
                        )
                        
                except httpx.ConnectError:
                    return ChatResponse(
                        response=f"❌ 无法连接到 LangGraph 后端服务\n\n请确保已启动 LangGraph Dev Studio：\n\n```bash\nuvx --refresh --from \"langgraph-cli[inmem]\" --with-editable . langgraph dev\n```\n\n当前配置的后端地址: {LANGRAPH_BASE_URL}\n\n或者运行代理服务：\n```bash\npython backend_proxy.py\n```",
                        conversation_id=thread_id
                    )
                except httpx.TimeoutException:
                    return ChatResponse(
                        response="⏱️ 请求超时，请稍后重试",
                        conversation_id=thread_id
                    )
                except Exception as e:
                    return ChatResponse(
                        response=f"处理请求时出错: {str(e)}",
                        conversation_id=thread_id
                    )
                    
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"服务器错误: {str(e)}")

    @app.post("/transcribe")
    async def transcribe(
        audio: UploadFile = File(...),
        agent: str = Form(...)
    ):
        """
        处理语音转录请求
        """
        # 读取音频文件
        audio_data = await audio.read()
        
        # 这里应该调用语音识别服务（如 OpenAI Whisper API）
        # 目前返回提示信息
        return {
            "text": "语音识别功能需要配置语音识别服务（如 OpenAI Whisper API）",
            "transcription": "语音识别功能需要配置语音识别服务",
            "note": "音频文件已接收，大小: {} 字节".format(len(audio_data))
        }

    @app.get("/health")
    async def health():
        """健康检查"""
        return {
            "status": "healthy",
            "langgraph_url": LANGRAPH_BASE_URL,
            "fastapi": True
        }

    if __name__ == "__main__":
        import uvicorn
        port = int(os.getenv("PORT", 8123))
        print(f"🚀 启动 DecideX 后端代理服务...")
        print(f"📡 LangGraph 后端地址: {LANGRAPH_BASE_URL}")
        print(f"🌐 代理服务地址: http://localhost:{port}")
        print(f"📝 API 文档: http://localhost:{port}/docs")
        uvicorn.run(app, host="0.0.0.0", port=port)
else:
    print("请先安装依赖: pip install fastapi uvicorn")
