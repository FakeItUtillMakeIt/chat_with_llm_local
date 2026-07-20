#!/bin/bash
# 企业微信服务一键启动（使用 tmux）
# 需要安装 tmux: sudo apt install tmux

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")/server"
PORT=9800
SESSION="wecom"

cd "$PROJECT_DIR"

# 检查 tmux
if ! command -v tmux &> /dev/null; then
    echo "tmux 未安装，请先安装：sudo apt install tmux"
    exit 1
fi

# 停止旧的 tmux session
tmux kill-session -t $SESSION 2>/dev/null || true
sleep 1

echo "=========================================="
echo "  企业微信服务一键启动"
echo "=========================================="
echo ""

# 创建 tmux session
tmux new-session -d -s $SESSION -n mcp
tmux send-keys -t $SESSION:mcp "python mcp-server/wecom/mcp-wecom.py --port $PORT" Enter

tmux new-window -t $SESSION -n serveo
tmux send-keys -t $SESSION:serveo "bash $SCRIPT_DIR/run-serveo.sh $PORT" Enter

echo "已启动 tmux session: $SESSION"
echo ""
echo "查看服务状态："
echo "  tmux attach -t $SESSION"
echo ""
echo "切换窗口：Ctrl+B 然后按 0 或 1"
echo "分离会话：Ctrl+B 然后按 D"
echo ""
echo "停止所有服务："
echo "  tmux kill-session -t $SESSION"
echo ""

# 等待几秒后显示状态
sleep 3
echo "=== MCP 服务器日志 ==="
tmux capture-pane -t $SESSION:mcp -p | tail -5
echo ""
echo "=== serveo 日志 ==="
tmux capture-pane -t $SESSION:serveo -p | tail -5
