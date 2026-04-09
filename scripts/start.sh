#!/bin/bash
# Job OS 启动脚本
set -e

cd "$(dirname "$0")/.."

PORT=${PORT:-8891}

# 检查依赖
if ! /usr/bin/python3 -c "import fastapi" 2>/dev/null; then
    echo "📦 安装依赖..."
    /usr/bin/python3 -m pip install --user -r requirements.txt
fi

echo "🚀 启动 Job OS BFF on port $PORT"
echo "   Web UI: http://localhost:$PORT/"
echo "   API:    http://localhost:$PORT/api/v1/health"
echo "   Docs:   http://localhost:$PORT/docs"
echo ""
echo "按 Ctrl+C 停止"
echo ""

/usr/bin/python3 -m server.main --port $PORT
