#!/bin/bash
# 企业微信服务一键启动（使用 serveo 内网穿透）

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")/server"
PORT=9800

cd "$PROJECT_DIR"

echo "=========================================="
echo "  企业微信服务一键启动"
echo "=========================================="
echo ""

# 停止旧进程
pkill -f "mcp-wecom.py" 2>/dev/null || true
pkill -f "serveo" 2>/dev/null || true
sleep 1

# 启动 WeCom MCP 服务器
echo "[1/2] 启动 WeCom MCP 服务器..."
nohup python mcp-server/wecom/mcp-wecom.py --port $PORT < /dev/null > /tmp/wecom-mcp.log 2>&1 &
MCP_PID=$!
sleep 3

# 检查是否启动成功（检查日志中是否有启动成功消息）
if ! grep -q "回调服务器已启动" /tmp/wecom-mcp.log 2>/dev/null; then
    echo "MCP 服务器启动失败，日志："
    cat /tmp/wecom-mcp.log
    exit 1
fi
echo "  ✓ MCP 服务器已启动 (PID: $MCP_PID)"

# 启动 serveo 内网穿透
echo ""
echo "[2/2] 启动 serveo 内网穿透..."

SSH_OPTS="-o StrictHostKeyChecking=no -o ServerAliveInterval=60"

# 如果有代理，添加代理设置
if [ -n "$HTTP_PROXY" ]; then
    PROXY_HOST=$(echo "$HTTP_PROXY" | sed 's|http://||' | sed 's|.*@||' | cut -d: -f1)
    PROXY_PORT=$(echo "$HTTP_PROXY" | sed 's|http://||' | sed 's|.*@||' | cut -d: -f2)
    if [ -n "$PROXY_HOST" ] && [ -n "$PROXY_PORT" ]; then
        echo "  使用代理: $PROXY_HOST:$PROXY_PORT"
        SSH_OPTS="$SSH_OPTS -o ProxyCommand='nc -x $PROXY_HOST:$PROXY_PORT -X connect %h %p'"
    fi
fi

# 启动 serveo 并捕获 URL
ssh $SSH_OPTS -R 80:localhost:$PORT serveo.net > /tmp/serveo.log 2>&1 &
SERVEO_PID=$!

# 等待 serveo 输出 URL
echo "  等待 serveo 分配 URL..."
SERVEO_URL=""
for i in $(seq 1 15); do
    sleep 1
    SERVEO_URL=$(grep -oP 'https://[a-zA-Z0-9-]+\.serveousercontent\.com' /tmp/serveo.log 2>/dev/null | head -1)
    if [ -n "$SERVEO_URL" ]; then
        break
    fi
done

echo ""
echo "=========================================="
echo "  启动完成！"
echo "=========================================="
echo ""

if [ -n "$SERVEO_URL" ]; then
    echo "  回调 URL（填入企业微信后台）："
    echo ""
    echo "  ${SERVEO_URL}/wecom/callback"
    echo ""
    echo "  测试地址（浏览器打开）："
    echo "  ${SERVEO_URL}/wecom/callback"
else
    echo "  ⚠ serveo URL 获取失败"
    echo "  请手动查看：cat /tmp/serveo.log"
    echo ""
    echo "  或手动运行："
    echo "  ssh -R 80:localhost:$PORT serveo.net"
fi

echo ""
echo "=========================================="
echo "  按 Ctrl+C 停止所有服务"
echo "=========================================="

cleanup() {
    echo ""
    echo "正在停止服务..."
    kill $MCP_PID 2>/dev/null || true
    kill $SERVEO_PID 2>/dev/null || true
    pkill -f "mcp-wecom.py" 2>/dev/null || true
    pkill -f "serveo" 2>/dev/null || true
    echo "已停止"
    exit 0
}

trap cleanup INT TERM
wait
