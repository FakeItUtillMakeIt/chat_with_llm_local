import os
import asyncio
from contextlib import AsyncExitStack
from typing import Any, Dict, List

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from openai import OpenAI
from dotenv import load_dotenv
import json

load_dotenv()

DEFAULT_CONFIG_PATH = "mcp_config.json"
DEFAULT_MODEL = os.getenv("LLM_MODEL", "LongCat-Flash-Chat")
DEFAULT_BASE_URL = os.getenv("LLM_BASE_URL", "https://api.longcat.chat/openai/v1")
DEFAULT_API_KEY = os.getenv("LLM_API_KEY", "")


class LLM_MCP:
    """MCP 多服务器客户端"""

    def __init__(self, config_path: str = DEFAULT_CONFIG_PATH, system_prompt: str = None):
        self.sessions: Dict[str, ClientSession] = {}
        self.exit_stack = AsyncExitStack()
        api_key = DEFAULT_API_KEY or os.getenv("OPENAI_API_KEY", "placeholder")
        base_url = DEFAULT_BASE_URL or os.getenv("OPENAI_BASE_URL")
        kwargs = {"api_key": api_key}
        if base_url:
            kwargs["base_url"] = base_url
        self.llm = OpenAI(**kwargs)
        self.model = DEFAULT_MODEL
        self.config_path = config_path
        self.config = self._load_config()
        self.system_prompt = system_prompt

    def _load_config(self) -> dict:
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except FileNotFoundError:
            print(f"配置文件 {self.config_path} 不存在，将使用空配置")
            return {"servers": {}, "default_servers": []}
        except json.JSONDecodeError as e:
            raise ValueError(f"配置文件格式错误: {e}")

    def _get_server_config(self, server_name: str) -> Dict[str, Any]:
        servers = self.config.get("servers", {})
        if server_name not in servers:
            raise ValueError(f"服务器 '{server_name}' 未在配置文件中找到")
        cfg = servers[server_name]
        if "script_path" not in cfg:
            raise ValueError(f"服务器 '{server_name}' 缺少必须字段: script_path")
        if not isinstance(cfg.get("args", []), list):
            raise ValueError(f"服务器 '{server_name}' 的 args 必须是数组(list)")
        if not isinstance(cfg.get("env", {}), dict):
            raise ValueError(f"服务器 '{server_name}' 的 env 必须是字典(dict)")
        return cfg

    def _detect_server_type(self, script_path: str, declared_type: str) -> str:
        st = (declared_type or "auto").lower()
        if st in ("python", "node"):
            return st
        if st == "auto":
            lower = script_path.lower()
            if lower.endswith('.py'):
                return "python"
            if lower.endswith('.js'):
                return "node"
            raise ValueError(f"无法自动检测服务器类型: {script_path}")
        raise ValueError(f"不支持的服务器类型: {declared_type}")

    def _build_server_params(self, script_path: str, server_type: str, server_args: List[str], env: Dict[str, str]) -> StdioServerParameters:
        command = "python" if server_type == "python" else "node"
        return StdioServerParameters(
            command=command,
            args=[script_path, *server_args],
            env=env
        )

    async def _start_session(self, server_name: str, server_params: StdioServerParameters) -> ClientSession:
        stdio, write = await self.exit_stack.enter_async_context(stdio_client(server_params))
        session = await self.exit_stack.enter_async_context(ClientSession(stdio, write))
        await session.initialize()
        self.sessions[server_name] = session
        return session

    async def connect_to_server(self, server_name: str, server_config: dict = None):
        try:
            server_config = server_config or self._get_server_config(server_name)
            script_path: str = server_config["script_path"]
            declared_type: str = server_config.get("type", "auto")
            server_args: List[str] = server_config.get("args", [])
            env: Dict[str, str] = server_config.get("env", {})

            server_type = self._detect_server_type(script_path, declared_type)
            server_params = self._build_server_params(script_path, server_type, server_args, env)
            session = await self._start_session(server_name, server_params)

            response = await session.list_tools()
            tools = response.tools
            print(f"已连接到服务器 '{server_name}'，工具包括：{[tool.name for tool in tools]}")

        except Exception as e:
            details = (
                f"连接服务器 '{server_name}' 失败。\n"
                "可能原因：\n"
                "- 服务器脚本在启动后崩溃或提前退出\n"
                "- 服务器向 stdout 打印了日志，破坏了 MCP JSON-RPC 协议\n"
                "- 服务器脚本需要额外参数\n"
                f"配置: {server_config}"
            )
            raise RuntimeError(details) from e

    async def connect_all_default_servers(self):
        default_servers = self.config.get("default_servers", [])
        if not default_servers:
            print("未指定默认服务器")
            return

        for server_name in default_servers:
            try:
                await self.connect_to_server(server_name)
            except Exception as e:
                print(f"连接服务器 '{server_name}' 失败: {e}")

    async def connect_all_servers(self):
        for server_name in self.config["servers"]:
            try:
                await self.connect_to_server(server_name)
            except Exception as e:
                print(f"连接服务器 '{server_name}' 失败: {e}")

    async def list_all_tools(self):
        all_tools = []
        for server_name, session in self.sessions.items():
            try:
                response = await session.list_tools()
                for tool in response.tools:
                    tool_with_prefix = {
                        "name": f"{server_name}:{tool.name}",
                        "description": f"[{server_name}] {tool.description}",
                        "inputSchema": tool.inputSchema,
                        "server_name": server_name,
                        "original_name": tool.name
                    }
                    all_tools.append(tool_with_prefix)
            except Exception as e:
                print(f"获取服务器 '{server_name}' 工具列表失败: {e}")
        return all_tools

    async def call_tool_by_name(self, tool_name: str, args: dict):
        server_name, original_tool_name = tool_name.split(":", 1)
        if server_name not in self.sessions:
            raise ValueError(f"服务器 '{server_name}' 未连接")
        session = self.sessions[server_name]
        return await session.call_tool(original_tool_name, args)

    async def process_query(self, query: str) -> str:
        """使用 LLM 和可用的工具处理查询"""
        if not self.sessions:
            return "错误：没有连接到任何MCP服务器。请检查配置文件。"

        messages = []
        if self.system_prompt:
            messages.append({"role": "system", "content": self.system_prompt})
        messages.append({"role": "user", "content": query})

        all_tools = await self.list_all_tools()
        available_tools = [{
            "type": "function",
            "function": {
                "name": tool["name"],
                "description": tool["description"],
                "parameters": tool["inputSchema"]
            }
        } for tool in all_tools]

        response = self.llm.chat.completions.create(
            model=self.model,
            max_tokens=1000,
            messages=messages,
            tools=available_tools
        )

        message = response.choices[0].message

        # 工具调用循环
        while hasattr(message, 'tool_calls') and message.tool_calls:
            tool_results = []
            for tool_call in message.tool_calls:
                tool_name = tool_call.function.name
                tool_args = json.loads(tool_call.function.arguments) if isinstance(tool_call.function.arguments, str) else tool_call.function.arguments

                print(f"  [调用工具] {tool_name}({tool_args})")
                result = await self.call_tool_by_name(tool_name, tool_args)
                print(f"  [工具结果] {result.content}")

                tool_results.append({
                    "role": "tool",
                    "content": str(result.content),
                    "tool_call_id": tool_call.id
                })

            messages.append({
                "role": "assistant",
                "content": message.content or "",
                "tool_calls": [{
                    "id": tc.id,
                    "type": "function",
                    "function": {"name": tc.function.name, "arguments": tc.function.arguments}
                } for tc in message.tool_calls]
            })
            messages.extend(tool_results)

            response = self.llm.chat.completions.create(
                model=self.model,
                max_tokens=1000,
                messages=messages,
                tools=available_tools
            )
            message = response.choices[0].message

        return message.content or ""

    async def chat_loop(self):
        print("\nMCP 客户端已启动！")
        print("输入你的查询或输入 'quit' 退出。")

        while True:
            try:
                query = input("\n查询: ").strip()
                if query.lower() == 'quit':
                    break
                response = await self.process_query(query)
                print("\n" + response)
            except Exception as e:
                print(f"\n错误: {str(e)}")

    async def cleanup(self):
        await self.exit_stack.aclose()


async def main():
    import argparse

    parser = argparse.ArgumentParser(description="MCP智能客户端")
    parser.add_argument("--config", "-c", default="mcp_config.json", help="配置文件路径")
    parser.add_argument("--server", "-s", action="append", metavar="NAME", help="指定服务器")
    parser.add_argument("--all", "-a", action="store_true", help="连接所有服务器")
    args = parser.parse_args()

    client = LLM_MCP(config_path=args.config)
    try:
        if args.server:
            for server_name in args.server:
                await client.connect_to_server(server_name)
        elif args.all:
            await client.connect_all_servers()
        else:
            await client.connect_all_default_servers()

        if not client.sessions:
            print("未连接到任何服务器，退出。")
            return

        await client.chat_loop()
    finally:
        await client.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
