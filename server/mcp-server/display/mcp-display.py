#!/usr/bin/env python3
"""MCP Display Server - 屏幕亮度控制工具（支持Windows/WSL/Linux/macOS）"""

import platform
import subprocess
import sys
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

app = Server("display")

SYSTEM = platform.system()


@app.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="get_brightness",
            description="获取当前屏幕亮度（百分比）",
            inputSchema={
                "type": "object",
                "properties": {}
            }
        ),
        Tool(
            name="set_brightness",
            description="设置屏幕亮度（0-100%）",
            inputSchema={
                "type": "object",
                "properties": {
                    "percent": {
                        "type": "number",
                        "description": "亮度百分比，0-100之间的整数"
                    }
                },
                "required": ["percent"]
            }
        )
    ]


@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    try:
        if name == "get_brightness":
            return await get_brightness()
        elif name == "set_brightness":
            percent = arguments["percent"]
            return await set_brightness(percent)
        else:
            return [TextContent(type="text", text=f"未知工具: {name}")]
    except Exception as e:
        return [TextContent(type="text", text=f"错误: {str(e)}")]


async def get_brightness() -> list[TextContent]:
    """获取屏幕亮度"""

    if SYSTEM == "Windows" or _is_wsl():
        ps_script = '''
$OutputEncoding = [System.Text.Encoding]::UTF8
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
(Get-WmiObject -Namespace root/WMI -Class WmiMonitorBrightness).CurrentBrightness
'''
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", ps_script],
            capture_output=True, timeout=10
        )
        if result.returncode != 0:
            stderr = result.stderr.decode("utf-8", errors="replace").strip()
            return [TextContent(type="text", text=f"获取亮度失败: {stderr}")]

        brightness = result.stdout.decode("utf-8", errors="replace").strip()
        if brightness.isdigit():
            return [TextContent(type="text", text=f"当前亮度: {brightness}%")]
        if _is_wsl():
            return [TextContent(type="text", text="WSL 环境下无法通过 WMI 获取屏幕亮度（需要原生 Windows 环境）")]
        return [TextContent(type="text", text=f"无法解析亮度值: {brightness}")]

    elif SYSTEM == "Linux":
        result = subprocess.run(
            ["brightnessctl", "get"],
            capture_output=True, timeout=5
        )
        if result.returncode == 0:
            current = result.stdout.decode("utf-8", errors="replace").strip()
            max_result = subprocess.run(
                ["brightnessctl", "max"],
                capture_output=True, timeout=5
            )
            if max_result.returncode == 0:
                max_val = max_result.stdout.decode("utf-8", errors="replace").strip()
                if current.isdigit() and max_val.isdigit() and int(max_val) > 0:
                    pct = round(int(current) / int(max_val) * 100)
                    return [TextContent(type="text", text=f"当前亮度: {pct}%")]
            return [TextContent(type="text", text=f"当前亮度原始值: {current}")]
        else:
            return [TextContent(type="text", text="获取亮度失败（请安装 brightnessctl）")]

    elif SYSTEM == "Darwin":
        result = subprocess.run(
            ["osascript", "-e",
             'tell application "System Events" to get value of slider 1 of tab group 1 of window 1 of process "System Preferences"'],
            capture_output=True, timeout=10
        )
        if result.returncode == 0:
            val = result.stdout.decode("utf-8", errors="replace").strip()
            return [TextContent(type="text", text=f"当前亮度: {val}%")]
        return [TextContent(type="text", text="获取亮度失败")]

    return [TextContent(type="text", text=f"不支持的操作系统: {SYSTEM}")]


async def set_brightness(percent) -> list[TextContent]:
    """设置屏幕亮度"""

    try:
        percent = int(percent)
    except (ValueError, TypeError):
        return [TextContent(type="text", text="亮度值必须是0-100之间的整数")]

    if percent < 0 or percent > 100:
        return [TextContent(type="text", text="亮度值必须在0-100之间")]

    if SYSTEM == "Windows" or _is_wsl():
        ps_script = f'''
$OutputEncoding = [System.Text.Encoding]::UTF8
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$monitor = Get-WmiObject -Namespace root/WMI -Class WmiMonitorBrightnessMethods
$monitor.WmiSetBrightness(1, {percent})
'''
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", ps_script],
            capture_output=True, timeout=10
        )
        if result.returncode == 0:
            return [TextContent(type="text", text=f"亮度已设置为 {percent}%")]
        else:
            stderr = result.stderr.decode("utf-8", errors="replace").strip()
            return [TextContent(type="text", text=f"设置亮度失败: {stderr}")]

    elif SYSTEM == "Linux":
        result = subprocess.run(
            ["brightnessctl", "set", f"{percent}%"],
            capture_output=True, timeout=5
        )
        if result.returncode == 0:
            return [TextContent(type="text", text=f"亮度已设置为 {percent}%")]
        else:
            stderr = result.stderr.decode("utf-8", errors="replace").strip()
            return [TextContent(type="text", text=f"设置亮度失败: {stderr}")]

    elif SYSTEM == "Darwin":
        result = subprocess.run(
            ["osascript", "-e",
             f'tell application "System Events" to set value of slider 1 of tab group 1 of window 1 of process "System Preferences" to {percent / 100}'],
            capture_output=True, timeout=10
        )
        if result.returncode == 0:
            return [TextContent(type="text", text=f"亮度已设置为 {percent}%")]
        else:
            stderr = result.stderr.decode("utf-8", errors="replace").strip()
            return [TextContent(type="text", text=f"设置亮度失败: {stderr}")]

    return [TextContent(type="text", text=f"不支持的操作系统: {SYSTEM}")]


def _is_wsl() -> bool:
    """检测是否在 WSL 环境中"""
    if SYSTEM != "Linux":
        return False
    try:
        with open("/proc/version", "r") as f:
            version_info = f.read().lower()
            return "microsoft" in version_info or "wsl" in version_info
    except Exception:
        return False


async def main():
    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
