#!/bin/bash

# DecideX 前端启动脚本

echo "🚀 启动 DecideX 前端服务器..."

# 检查 Python 是否安装
if command -v python3 &> /dev/null; then
    echo "使用 Python 启动服务器..."
    cd "$(dirname "$0")"
    python3 -m http.server 8000
elif command -v python &> /dev/null; then
    echo "使用 Python 启动服务器..."
    cd "$(dirname "$0")"
    python -m http.server 8000
else
    echo "❌ 未找到 Python，请安装 Python 3 或使用其他方式启动服务器"
    echo ""
    echo "其他启动方式："
    echo "  - Node.js: npx http-server -p 8000"
    echo "  - PHP: php -S localhost:8000"
    exit 1
fi
