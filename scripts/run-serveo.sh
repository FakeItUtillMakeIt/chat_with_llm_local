#!/bin/bash
# serveo 内网穿透启动脚本
# 在另一个终端运行此脚本

set -e

PORT=${1:-9800}

echo "=========================================="
echo "  serveo 内网穿透"
echo "=========================================="
echo ""
echo "本地端口: $PORT"
echo ""

SSH_OPTS="-o StrictHostKeyChecking=no -o ServerAliveInterval=60"

# 如果有代理，添加代理设置
if [ -n "$HTTP_PROXY" ]; then
    PROXY_HOST=$(echo "$HTTP_PROXY" | sed 's|http://||' | sed 's|.*@||' | cut -d: -f1)
    PROXY_PORT=$(echo "$HTTP_PROXY" | sed 's|http://||' | sed 's|.*@||' | cut -d: -f2)
    if [ -n "$PROXY_HOST" ] && [ -n "$PROXY_PORT" ]; then
        echo "使用代理: $PROXY_HOST:$PROXY_PORT"
        SSH_OPTS="$SSH_OPTS -o ProxyCommand='nc -x $PROXY_HOST:$PROXY_PORT -X connect %h %p'"
    fi
fi

echo "正在连接 serveo..."
echo "按 Ctrl+C 停止"
echo ""

ssh $SSH_OPTS -R 80:localhost:$PORT serveo.net
