#!/bin/bash
# 内网穿透工具 - 支持代理环境
# 可选: serveo / localtunnel / cloudflared

set -e

PORT=9800
echo "=========================================="
echo "  内网穿透启动 (支持代理)"
echo "=========================================="
echo ""

# 方法1: serveo (SSH 方式，最可靠)
start_serveo() {
    echo "使用 serveo (SSH 反向隧道)..."
    echo ""

    # 配置 SSH 通过代理
    SSH_PROXY=""
    if [ -n "$HTTP_PROXY" ]; then
        PROXY_HOST=$(echo "$HTTP_PROXY" | sed 's|http://||' | sed 's|.*@||')
        SSH_PROXY="-o ProxyCommand='nc -x $PROXY_HOST -X connect %h %p'"
    fi

    # 启动 serveo
    ssh -o StrictHostKeyChecking=no \
        -o ServerAliveInterval=60 \
        $SSH_PROXY \
        -R 80:localhost:$PORT \
        serveo.net 2>&1 &

    SERVEO_PID=$!
    sleep 5

    # 获取 URL
    # serveo 会在输出中显示 URL
    SERVEO_URL=$(ss -tlnp 2>/dev/null | grep $PORT || true)

    echo "serveo 已启动 (PID: $SERVEO_PID)"
    echo "请查看上方输出中的 URL"
    echo ""
    echo "如果 URL 未显示，请手动运行："
    echo "  ssh -R 80:localhost:$PORT serveo.net"
    return $SERVEO_PID
}

# 方法2: localtunnel (Node.js)
start_localtunnel() {
    echo "使用 localtunnel..."

    if ! command -v npx &> /dev/null; then
        echo "npx 未安装，请先安装 Node.js"
        return 1
    fi

    npx -y localtunnel --port $PORT 2>&1 &
    LT_PID=$!
    sleep 5

    echo "localtunnel 已启动 (PID: $LT_PID)"
    echo "请查看上方输出中的 URL"
    return $LT_PID
}

# 方法3: cloudflared (Cloudflare 隧道)
start_cloudflared() {
    echo "使用 cloudflared..."

    if ! command -v cloudflared &> /dev/null; then
        echo "cloudflared 未安装，正在下载..."
        curl -L https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 -o /tmp/cloudflared
        chmod +x /tmp/cloudflared
        sudo mv /tmp/cloudflared /usr/local/bin/ 2>/dev/null || mv /tmp/cloudflared ~/bin/ 2>/dev/null
    fi

    cloudflared tunnel --url http://localhost:$PORT 2>&1 &
    CF_PID=$!
    sleep 8

    echo "cloudflared 已启动 (PID: $CF_PID)"
    echo "请查看上方输出中的 URL"
    return $CF_PID
}

# 选择方法
echo "选择穿透方案："
echo "  1) serveo (SSH，最推荐，无需安装)"
echo "  2) localtunnel (Node.js，需要 npx)"
echo "  3) cloudflared (Cloudflare，需要下载)"
echo ""
read -p "请选择 [1-3]: " choice

case $choice in
    1) start_serveo ;;
    2) start_localtunnel ;;
    3) start_cloudflared ;;
    *) echo "无效选择"; exit 1 ;;
esac

echo ""
echo "按 Ctrl+C 停止"
echo "=========================================="

trap "kill $SERVEO_PID $LT_PID $CF_PID 2>/dev/null; exit 0" INT TERM
wait
