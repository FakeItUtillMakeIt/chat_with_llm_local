#!/bin/bash
# serveo 内网穿透 - 最简单可靠的方案
# 无需安装任何工具，只需要 SSH

set -e

PORT=${1:-9800}
echo "=========================================="
echo "  serveo 内网穿透"
echo "=========================================="
echo ""
echo "本地端口: $PORT"
echo ""

# 检查 SSH 代理设置
SSH_OPTS="-o StrictHostKeyChecking=no -o ServerAliveInterval=60"

if [ -n "$HTTP_PROXY" ]; then
    PROXY_HOST=$(echo "$HTTP_PROXY" | sed 's|http://||' | sed 's|.*@||' | cut -d: -f1)
    PROXY_PORT=$(echo "$HTTP_PROXY" | sed 's|http://||' | sed 's|.*@||' | cut -d: -f2)
    echo "检测到代理: $PROXY_HOST:$PROXY_PORT"
    SSH_OPTS="$SSH_OPTS -o ProxyCommand='nc -x $PROXY_HOST:$PROXY_PORT -X connect %h %p'"
fi

echo "正在连接 serveo..."
echo ""
echo "=========================================="
echo "  你的回调 URL 会是这种格式："
echo "  https://xxxx.serveo.net/wecom/callback"
echo "=========================================="
echo ""

# 启动 serveo
ssh $SSH_OPTS -R 80:localhost:$PORT serveo.net
