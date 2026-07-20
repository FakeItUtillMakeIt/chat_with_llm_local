#!/bin/bash
# 企业微信服务启动脚本
# 使用方法：在两个终端分别运行
#   终端1: bash scripts/run-wecom-mcp.sh
#   终端2: bash scripts/run-serveo.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")/server"
PORT=9800

cd "$PROJECT_DIR"

echo "=========================================="
echo "  企业微信 MCP 服务器"
echo "=========================================="
echo ""
echo "启动回调服务器 (端口 $PORT)..."
echo "按 Ctrl+C 停止"
echo ""

# 直接运行（前台）
python mcp-server/wecom/mcp-wecom.py --port $PORT
