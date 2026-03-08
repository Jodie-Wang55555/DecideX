#!/bin/bash

# DecideX 后端启动脚本

echo "🚀 启动 DecideX 后端服务..."

# 检查是否安装了 FastAPI
if ! python3 -c "import fastapi" 2>/dev/null; then
    echo "⚠️  未检测到 FastAPI，正在安装..."
    pip install fastapi uvicorn python-multipart
fi

# 启动后端代理服务
echo "📡 启动后端代理服务（端口 8123）..."
python3 backend_proxy.py
