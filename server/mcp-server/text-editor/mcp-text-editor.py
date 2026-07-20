#!/usr/bin/env python3
"""MCP Text Editor Server - 提供文件读写和编辑功能"""

import os
import subprocess
import sys
from pathlib import Path
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

app = Server("text-editor")


@app.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="read_file",
            description="读取指定文件的内容",
            inputSchema={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "要读取的文件路径（绝对路径或相对路径）"
                    }
                },
                "required": ["path"]
            }
        ),
        Tool(
            name="write_file",
            description="将内容写入指定文件（覆盖原有内容）",
            inputSchema={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "要写入的文件路径"
                    },
                    "content": {
                        "type": "string",
                        "description": "要写入的文件内容"
                    }
                },
                "required": ["path", "content"]
            }
        ),
        Tool(
            name="append_file",
            description="在指定文件末尾追加内容",
            inputSchema={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "要追加内容的文件路径"
                    },
                    "content": {
                        "type": "string",
                        "description": "要追加的内容"
                    }
                },
                "required": ["path", "content"]
            }
        ),
        Tool(
            name="open_in_editor",
            description="用系统默认编辑器打开文件",
            inputSchema={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "要打开的文件路径"
                    },
                    "editor": {
                        "type": "string",
                        "description": "编辑器命令（可选，如 code、nano、vim）。不指定则使用系统默认"
                    }
                },
                "required": ["path"]
            }
        ),
        Tool(
            name="list_directory",
            description="列出指定目录下的文件和子目录",
            inputSchema={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "要列出的目录路径"
                    }
                },
                "required": ["path"]
            }
        )
    ]


@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    try:
        if name == "read_file":
            return await read_file(arguments["path"])
        elif name == "write_file":
            return await write_file(arguments["path"], arguments["content"])
        elif name == "append_file":
            return await append_file(arguments["path"], arguments["content"])
        elif name == "open_in_editor":
            editor = arguments.get("editor")
            return await open_in_editor(arguments["path"], editor)
        elif name == "list_directory":
            return await list_directory(arguments["path"])
        else:
            return [TextContent(type="text", text=f"未知工具: {name}")]
    except Exception as e:
        return [TextContent(type="text", text=f"错误: {str(e)}")]


async def read_file(path: str) -> list[TextContent]:
    file_path = Path(path).expanduser().resolve()
    if not file_path.exists():
        return [TextContent(type="text", text=f"文件不存在: {path}")]
    if not file_path.is_file():
        return [TextContent(type="text", text=f"路径不是文件: {path}")]

    try:
        content = file_path.read_text(encoding="utf-8")
        return [TextContent(type="text", text=content)]
    except UnicodeDecodeError:
        return [TextContent(type="text", text=f"无法以UTF-8编码读取文件（可能是二进制文件）: {path}")]
    except PermissionError:
        return [TextContent(type="text", text=f"没有权限读取文件: {path}")]
    except Exception as e:
        return [TextContent(type="text", text=f"读取文件失败: {str(e)}")]


async def write_file(path: str, content: str) -> list[TextContent]:
    file_path = Path(path).expanduser().resolve()

    if file_path.exists() and not file_path.is_file():
        return [TextContent(type="text", text=f"路径存在但不是文件: {path}")]

    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(content, encoding="utf-8")
    return [TextContent(type="text", text=f"文件已写入: {file_path}")]


async def append_file(path: str, content: str) -> list[TextContent]:
    file_path = Path(path).expanduser().resolve()

    if file_path.exists() and not file_path.is_file():
        return [TextContent(type="text", text=f"路径存在但不是文件: {path}")]

    file_path.parent.mkdir(parents=True, exist_ok=True)
    with open(file_path, "a", encoding="utf-8") as f:
        f.write(content)
    return [TextContent(type="text", text=f"内容已追加到文件: {file_path}")]


async def open_in_editor(path: str, editor: str = None) -> list[TextContent]:
    file_path = Path(path).expanduser().resolve()

    if not file_path.exists():
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text("", encoding="utf-8")

    if editor:
        cmd = [editor, str(file_path)]
    else:
        if sys.platform == "win32":
            cmd = ["notepad.exe", str(file_path)]
        elif sys.platform == "darwin":
            cmd = ["open", "-t", str(file_path)]
        else:
            cmd = ["xdg-open", str(file_path)]

    subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return [TextContent(type="text", text=f"已用 {editor or '默认编辑器'} 打开: {file_path}")]


async def list_directory(path: str) -> list[TextContent]:
    dir_path = Path(path).expanduser().resolve()

    if not dir_path.exists():
        return [TextContent(type="text", text=f"目录不存在: {path}")]
    if not dir_path.is_dir():
        return [TextContent(type="text", text=f"路径不是目录: {path}")]

    items = []
    for item in sorted(dir_path.iterdir()):
        prefix = "[DIR] " if item.is_dir() else "[FILE] "
        items.append(f"{prefix}{item.name}")

    if not items:
        return [TextContent(type="text", text=f"目录为空: {path}")]

    return [TextContent(type="text", text="\n".join(items))]


async def main():
    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
