#!/usr/bin/env python3
"""MCP WeCom Server - 企业微信消息收发工具"""

import os
import json
import time
import hashlib
import threading
import queue
import xml.etree.ElementTree as ET
from typing import Optional
from flask import Flask, request, jsonify

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False


# ==================== 配置 ====================
CORP_ID = os.getenv("WECOM_CORP_ID", "")
CORP_SECRET = os.getenv("WECOM_CORP_SECRET", "")
AGENT_ID = os.getenv("WECOM_AGENT_ID", "")
TOKEN = os.getenv("WECOM_TOKEN", "")
ENCODING_AES_KEY = os.getenv("WECOM_ENCODING_AES_KEY", "")
CALLBACK_URL = os.getenv("WECOM_CALLBACK_URL", "")
CALLBACK_PORT = int(os.getenv("WECOM_CALLBACK_PORT", "9800"))

# 消息队列（回调服务器 → MCP 工具）
message_queue = queue.Queue()
# 待发送消息队列（MCP 工具 → 发送线程）
send_queue = queue.Queue()

app = Flask(__name__)


# ==================== 企业微信 API 封装 ====================
class WeComAPI:
    """企业微信 API 封装"""

    BASE_URL = "https://qyapi.weixin.qq.com/cgi-bin"

    def __init__(self, corp_id: str, corp_secret: str, agent_id: str):
        self.corp_id = corp_id
        self.corp_secret = corp_secret
        self.agent_id = agent_id
        self._access_token = None
        self._token_expire_time = 0

    def get_access_token(self) -> Optional[str]:
        """获取 access_token（带缓存）"""
        if self._access_token and time.time() < self._token_expire_time:
            return self._access_token

        url = f"{self.BASE_URL}/gettoken"
        params = {"corpid": self.corp_id, "corpsecret": self.corp_secret}
        try:
            resp = requests.get(url, params=params, timeout=10)
            data = resp.json()
            if data.get("errcode") == 0:
                self._access_token = data["access_token"]
                self._token_expire_time = time.time() + 7000
                return self._access_token
            else:
                print(f"获取 token 失败: {data}")
        except Exception as e:
            print(f"获取 token 异常: {e}")
        return None

    def send_text_message(self, user_id: str, content: str) -> dict:
        """发送文本消息"""
        token = self.get_access_token()
        if not token:
            return {"errcode": -1, "errmsg": "无法获取 access_token"}

        url = f"{self.BASE_URL}/message/send?access_token={token}"
        payload = {
            "touser": user_id,
            "msgtype": "text",
            "agentid": self.agent_id,
            "text": {"content": content},
        }
        try:
            resp = requests.post(url, json=payload, timeout=10)
            return resp.json()
        except Exception as e:
            return {"errcode": -1, "errmsg": str(e)}

    def send_markdown_message(self, user_id: str, content: str) -> dict:
        """发送 Markdown 消息"""
        token = self.get_access_token()
        if not token:
            return {"errcode": -1, "errmsg": "无法获取 access_token"}

        url = f"{self.BASE_URL}/message/send?access_token={token}"
        payload = {
            "touser": user_id,
            "msgtype": "markdown",
            "agentid": self.agent_id,
            "markdown": {"content": content},
        }
        try:
            resp = requests.post(url, json=payload, timeout=10)
            return resp.json()
        except Exception as e:
            return {"errcode": -1, "errmsg": str(e)}

    def send_group_message(self, chat_id: str, content: str) -> dict:
        """发送群消息"""
        token = self.get_access_token()
        if not token:
            return {"errcode": -1, "errmsg": "无法获取 access_token"}

        url = f"{self.BASE_URL}/message/send?access_token={token}"
        payload = {
            "chatid": chat_id,
            "msgtype": "text",
            "agentid": self.agent_id,
            "text": {"content": content},
        }
        try:
            resp = requests.post(url, json=payload, timeout=10)
            return resp.json()
        except Exception as e:
            return {"errcode": -1, "errmsg": str(e)}


# ==================== 全局 WeCom API 实例 ====================
wecom_api = WeComAPI(CORP_ID, CORP_SECRET, AGENT_ID) if CORP_ID and CORP_SECRET and AGENT_ID else None


# ==================== Flask 回调服务器 ====================
def verify_signature(signature: str, timestamp: str, nonce: str, echo_str: str) -> Optional[str]:
    """验证回调签名"""
    if not TOKEN or not ENCODING_AES_KEY:
        return echo_str

    try:
        from Crypto.Cipher import AES
        import base64

        # 验证签名
        sha1 = hashlib.sha1()
        sort_list = sorted([TOKEN, timestamp, nonce, echo_str])
        sha1.update("".join(sort_list).encode("utf-8"))
        hashcode = sha1.hexdigest()

        if hashcode != signature:
            return None

        # 解密 echo_str
        aes_key = base64.b64decode(ENCODING_AES_KEY + "=")
        cipher = AES.new(aes_key, AES.MODE_CBC, aes_key[:16])
        decrypted = cipher.decrypt(base64.b64decode(echo_str))
        # 去除补位
        pad = decrypted[-1]
        decrypted = decrypted[:-pad]
        return decrypted[16:].decode("utf-8")
    except Exception as e:
        print(f"签名验证失败: {e}")
        return None


@app.route("/wecom/callback", methods=["GET"])
def wecom_verify():
    """验证回调 URL"""
    signature = request.args.get("msg_signature", "")
    timestamp = request.args.get("timestamp", "")
    nonce = request.args.get("nonce", "")
    echo_str = request.args.get("echostr", "")

    result = verify_signature(signature, timestamp, nonce, echo_str)
    if result is not None:
        return result
    return "验证失败", 403


@app.route("/wecom/callback", methods=["POST"])
def wecom_receive():
    """接收企业微信消息"""
    try:
        data = request.data
        root = ET.fromstring(data)

        msg_type = root.findtext("MsgType", "")
        user_id = root.findtext("FromUserName", "")
        content = root.findtext("Content", "")
        msg_id = root.findtext("MsgId", "")
        create_time = root.findtext("CreateTime", "")

        if msg_type == "text":
            # 放入消息队列
            message_queue.put({
                "type": "text",
                "user_id": user_id,
                "content": content,
                "msg_id": msg_id,
                "timestamp": create_time,
                "received_at": time.time(),
            })
            print(f"收到消息 [{user_id}]: {content[:50]}")

        return jsonify({"errcode": 0, "errmsg": "ok"})
    except Exception as e:
        print(f"处理消息异常: {e}")
        return jsonify({"errcode": -1, "errmsg": str(e)})


# ==================== MCP Server ====================
mcp_app = Server("wecom")


@mcp_app.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="send_message",
            description="发送文本消息给指定用户",
            inputSchema={
                "type": "object",
                "properties": {
                    "user_id": {
                        "type": "string",
                        "description": "用户 ID（企业微信中的 userID）"
                    },
                    "content": {
                        "type": "string",
                        "description": "消息内容"
                    }
                },
                "required": ["user_id", "content"]
            }
        ),
        Tool(
            name="send_markdown",
            description="发送 Markdown 格式消息",
            inputSchema={
                "type": "object",
                "properties": {
                    "user_id": {
                        "type": "string",
                        "description": "用户 ID"
                    },
                    "content": {
                        "type": "string",
                        "description": "Markdown 内容"
                    }
                },
                "required": ["user_id", "content"]
            }
        ),
        Tool(
            name="send_group_message",
            description="发送群消息",
            inputSchema={
                "type": "object",
                "properties": {
                    "chat_id": {
                        "type": "string",
                        "description": "群聊 ID"
                    },
                    "content": {
                        "type": "string",
                        "description": "消息内容"
                    }
                },
                "required": ["chat_id", "content"]
            }
        ),
        Tool(
            name="get_unread_messages",
            description="获取未读消息列表（从微信用户发来的消息）",
            inputSchema={
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "integer",
                        "description": "最大返回数量（默认 10）",
                        "default": 10
                    }
                }
            }
        ),
        Tool(
            name="get_status",
            description="获取企业微信连接状态",
            inputSchema={
                "type": "object",
                "properties": {}
            }
        ),
    ]


@mcp_app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    try:
        if name == "send_message":
            return await _send_text(arguments["user_id"], arguments["content"])
        elif name == "send_markdown":
            return await _send_markdown(arguments["user_id"], arguments["content"])
        elif name == "send_group_message":
            return await _send_group(arguments["chat_id"], arguments["content"])
        elif name == "get_unread_messages":
            return await _get_unread(arguments.get("limit", 10))
        elif name == "get_status":
            return await _get_status()
        else:
            return [TextContent(type="text", text=f"未知工具: {name}")]
    except Exception as e:
        return [TextContent(type="text", text=f"错误: {str(e)}")]


def shutdown_server():
    """关闭回调服务器"""
    func = request.environ.get("werkzeug.server.shutdown")
    if func:
        func()


async def _send_text(user_id: str, content: str) -> list[TextContent]:
    if not wecom_api:
        return [TextContent(type="text", text="企业微信未配置，请检查环境变量")]
    result = wecom_api.send_text_message(user_id, content)
    if result.get("errcode") == 0:
        return [TextContent(type="text", text=f"消息已发送")]
    else:
        return [TextContent(type="text", text=f"发送失败: {result}")]


async def _send_markdown(user_id: str, content: str) -> list[TextContent]:
    if not wecom_api:
        return [TextContent(type="text", text="企业微信未配置，请检查环境变量")]
    result = wecom_api.send_markdown_message(user_id, content)
    if result.get("errcode") == 0:
        return [TextContent(type="text", text=f"Markdown 消息已发送")]
    else:
        return [TextContent(type="text", text=f"发送失败: {result}")]


async def _send_group(chat_id: str, content: str) -> list[TextContent]:
    if not wecom_api:
        return [TextContent(type="text", text="企业微信未配置，请检查环境变量")]
    result = wecom_api.send_group_message(chat_id, content)
    if result.get("errcode") == 0:
        return [TextContent(type="text", text=f"群消息已发送")]
    else:
        return [TextContent(type="text", text=f"发送失败: {result}")]


async def _get_unread(limit: int) -> list[TextContent]:
    messages = []
    count = 0
    while count < limit and not message_queue.empty():
        try:
            msg = message_queue.get_nowait()
            messages.append(json.dumps(msg, ensure_ascii=False))
            count += 1
        except queue.Empty:
            break

    if not messages:
        return [TextContent(type="text", text="暂无未读消息")]

    return [TextContent(type="text", text="\n---\n".join(messages))]


async def _get_status() -> list[TextContent]:
    if not wecom_api:
        return [TextContent(type="text", text="状态: 未配置\n请设置 WECOM_CORP_ID, WECOM_CORP_SECRET, WECOM_AGENT_ID")]

    token = wecom_api.get_access_token()
    if token:
        return [TextContent(type="text", text=f"状态: 已连接\nCorpID: {CORP_ID[:6]}...\nAgentID: {AGENT_ID}")]
    else:
        return [TextContent(type="text", text="状态: 连接失败\n请检查配置")]


# ==================== 运行 ====================
# 全局退出事件
exit_event = threading.Event()


def start_callback_server(host: str = "0.0.0.0", port: int = 9800):
    """启动回调服务器（在后台线程）"""
    import logging
    import sys
    import os

    # 抑制所有 Flask/Werkzeug 输出
    log = logging.getLogger("werkzeug")
    log.setLevel(logging.CRITICAL)
    log.disabled = True

    # 禁用 Flask 启动信息
    cli = sys.modules.get("flask.cli")
    if cli:
        cli.show_server_banner = lambda *args, **kwargs: None

    def run_server():
        # 使用 app.run 而不是 make_server（更稳定）
        import logging
        log = logging.getLogger("werkzeug")
        log.setLevel(logging.CRITICAL)
        log.disabled = True

        cli = sys.modules.get("flask.cli")
        if cli:
            cli.show_server_banner = lambda *args, **kwargs: None

        app.run(host=host, port=port, debug=False, use_reloader=False)

    thread = threading.Thread(target=run_server, daemon=True)
    thread.start()

    # 等待服务器就绪（绕过代理）
    import time
    import os
    old_proxy = os.environ.get('http_proxy')
    os.environ['http_proxy'] = ''
    os.environ['https_proxy'] = ''
    os.environ['HTTP_PROXY'] = ''
    os.environ['HTTPS_PROXY'] = ''
    try:
        for _ in range(20):
            time.sleep(0.5)
            try:
                import urllib.request
                proxy_handler = urllib.request.ProxyHandler({})
                opener = urllib.request.build_opener(proxy_handler)
                opener.open(f"http://127.0.0.1:{port}/wecom/callback", timeout=2)
                break
            except Exception:
                pass
    finally:
        if old_proxy:
            os.environ['http_proxy'] = old_proxy

    print(f"企业微信回调服务器已启动: http://0.0.0.0:{port}/wecom/callback", file=sys.stderr)
    return thread


async def main():
    import argparse
    parser = argparse.ArgumentParser(description="企业微信 MCP 服务器")
    parser.add_argument("--port", type=int, default=CALLBACK_PORT, help="回调服务器端口")
    args = parser.parse_args()

    # 启动回调服务器
    start_callback_server(port=args.port)

    # 启动 MCP 服务器
    async with stdio_server() as (read_stream, write_stream):
        await mcp_app.run(read_stream, write_stream, mcp_app.create_initialization_options())


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
