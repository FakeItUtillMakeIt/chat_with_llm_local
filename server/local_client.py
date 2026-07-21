#!/usr/bin/env python3
"""
本地 LLM + MCP 客户端
支持语音对话和命令行两种模式
"""

import os
import sys
import json
import wave
import time
import asyncio
import argparse
import tempfile
import subprocess
from pathlib import Path
from datetime import datetime

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from llm_mcp import LLM_MCP
from tools.audio_to_text import AudioToText
from tools.offlineTTS import OfflineTTS

# 尝试导入音频相关库
try:
    import pyaudio
    PYAUDIO_AVAILABLE = True
except ImportError:
    PYAUDIO_AVAILABLE = False

try:
    import webrtcvad
    WEBRTCVAD_AVAILABLE = True
except ImportError:
    WEBRTCVAD_AVAILABLE = False


class LocalClient:
    """本地 LLM + MCP 客户端"""

    def __init__(self, config_path: str = "mcp_config.json", system_prompt: str = None):
        self.llm_client = LLM_MCP(config_path=config_path, system_prompt=system_prompt)
        self.asr = AudioToText()
        self.tts = OfflineTTS({"rate": 0, "volume": 100})

        # 音频参数
        self.sample_rate = 16000
        self.channels = 1
        self.bit_depth = 16
        self.frame_duration_ms = 30  # VAD 帧长度

        # 临时目录
        self.temp_dir = tempfile.mkdtemp(prefix="chat_llm_")

        # 检测音频能力
        self.audio_available = self._check_audio_available()

    def _check_audio_available(self) -> bool:
        """检查音频设备是否可用"""
        if not PYAUDIO_AVAILABLE:
            print("PyAudio 未安装，语音模式不可用")
            return False

        try:
            audio = pyaudio.PyAudio()
            input_count = 0
            for i in range(audio.get_device_count()):
                info = audio.get_device_info_by_index(i)
                if info.get("maxInputChannels", 0) > 0:
                    input_count += 1
                    print(f"  输入设备 {i}: {info['name']}")

            output_count = 0
            for i in range(audio.get_device_count()):
                info = audio.get_device_info_by_index(i)
                if info.get("maxOutputChannels", 0) > 0:
                    output_count += 1
                    print(f"  输出设备 {i}: {info['name']}")

            audio.terminate()

            if input_count == 0:
                print("未检测到麦克风，语音模式不可用")
                return False
            if output_count == 0:
                print("未检测到扬声器，语音模式不可用")
                return False

            return True
        except Exception as e:
            print(f"音频设备检测失败: {e}")
            return False

    def _record_audio_pyaudio(self, output_path: str) -> bool:
        """使用 PyAudio 录制音频（带 VAD 检测）"""
        audio = pyaudio.PyAudio()
        chunk_size = int(self.sample_rate * self.frame_duration_ms / 1000)

        stream = audio.open(
            format=pyaudio.paInt16,
            channels=self.channels,
            rate=self.sample_rate,
            input=True,
            frames_per_buffer=chunk_size
        )

        print("🎤 录音中...（静音2秒自动结束，或按 Ctrl+C 停止）")

        frames = []
        silent_chunks = 0
        max_silent_chunks = int(2000 / self.frame_duration_ms)  # 2秒静音
        speech_detected = False

        # 预热，丢弃前几帧
        for _ in range(5):
            stream.read(chunk_size, exception_on_overflow=False)

        vad = webrtcvad.Vad(2) if WEBRTCVAD_AVAILABLE else None

        try:
            while True:
                data = stream.read(chunk_size, exception_on_overflow=False)
                frames.append(data)

                # VAD 检测
                if vad and WEBRTCVAD_AVAILABLE:
                    try:
                        is_speech = vad.is_speech(data, self.sample_rate)
                        if is_speech:
                            speech_detected = True
                            silent_chunks = 0
                        else:
                            silent_chunks += 1
                    except Exception:
                        # VAD 失败时，使用简单的音量检测
                        silent_chunks = self._simple_vad(data, silent_chunks, speech_detected)
                        if silent_chunks == 0:
                            speech_detected = True
                else:
                    # 简单音量检测
                    silent_chunks = self._simple_vad(data, silent_chunks, speech_detected)
                    if silent_chunks == 0:
                        speech_detected = True

                # 检测到语音后，静音超过阈值则停止
                if speech_detected and silent_chunks >= max_silent_chunks:
                    print("🔇 检测到静音，录音结束")
                    break

                # 最长录音时间限制（60秒）
                if len(frames) * self.frame_duration_ms >= 60000:
                    print("⏰ 达到最大录音时长")
                    break

        except KeyboardInterrupt:
            print("\n⏹️ 手动停止录音")

        stream.stop_stream()
        stream.close()
        audio.terminate()

        if not speech_detected or len(frames) < 10:
            print("未检测到有效语音")
            return False

        # 保存 WAV
        with wave.open(output_path, "wb") as wf:
            wf.setnchannels(self.channels)
            wf.setsampwidth(self.bit_depth // 8)
            wf.setframerate(self.sample_rate)
            wf.writeframes(b"".join(frames))

        duration = len(frames) * self.frame_duration_ms / 1000
        print(f"✅ 录音完成，时长 {duration:.1f} 秒")
        return True

    def _simple_vad(self, data: bytes, silent_chunks: int, speech_detected: bool) -> int:
        """简单的音量检测 VAD"""
        import struct
        import math

        # 计算 RMS 音量
        count = len(data) // 2
        if count == 0:
            return silent_chunks + 1

        format_str = f"<{count}h"
        try:
            samples = struct.unpack(format_str, data)
            rms = math.sqrt(sum(s * s for s in samples) / count)
        except Exception:
            return silent_chunks + 1

        # 阈值判断
        threshold = 500  # 可根据实际环境调整
        if rms > threshold:
            return 0
        else:
            return silent_chunks + 1

    def _record_audio_powershell(self, output_path: str) -> bool:
        """使用 ffmpeg 录制音频（WSL 备用方案）"""
        result = subprocess.run(
            ["wslpath", "-w", output_path],
            capture_output=True
        )
        win_path = result.stdout.decode("utf-8", errors="replace").strip()

        ffmpeg_path = self._find_ffmpeg()
        if not ffmpeg_path:
            print("❌ 未找到 ffmpeg，请安装后重试")
            print("   安装方法：在 Windows PowerShell 中运行：winget install ffmpeg")
            return False

        print("🎤 录音中...（最长10秒）")

        # 获取系统默认录音设备
        mic_name = self._get_microphone_name(ffmpeg_path)
        if not mic_name:
            print("❌ 未找到麦克风设备")
            return False

        # 使用 PowerShell 执行 ffmpeg（支持 Windows 路径）
        ps_cmd = (
            f"& '{ffmpeg_path}' -y -f dshow -i 'audio={mic_name}' "
            f"-t 10 -ar 16000 -ac 1 -sample_fmt s16 '{win_path}'"
        )

        result = subprocess.run(
            ["powershell.exe", "-Command", ps_cmd],
            capture_output=True, timeout=20
        )

        if not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
            print("❌ 录音失败，请检查麦克风设备")
            print(f"   设备名: {mic_name}")
            stderr = result.stderr.decode("utf-8", errors="replace")[:200]
            if stderr:
                print(f"   错误: {stderr}")
            return False

        return True

    @staticmethod
    def _get_microphone_name(ffmpeg_path: str) -> str:
        """获取系统录音设备名称"""
        # 使用 PowerShell 执行 ffmpeg 并获取设备列表
        ps_cmd = f"& '{ffmpeg_path}' -list_devices true -f dshow -i dummy 2>&1"
        result = subprocess.run(
            ["powershell.exe", "-Command", ps_cmd],
            capture_output=True, timeout=15
        )
        # 合并 stdout 和 stderr（ffmpeg 输出到 stderr）
        output = (result.stdout + result.stderr).decode("utf-8", errors="replace")

        import re
        # 匹配 audio 设备行（支持中英文）
        matches = re.findall(r'"(.+?)" \(audio\)', output)
        if matches:
            # 优先选择非虚拟设备
            for name in matches:
                lower = name.lower()
                if 'virtual' not in lower and 'todect' not in lower:
                    return name
            # 否则返回第一个
            return matches[0]

        return ""

    def _play_audio_pyaudio(self, audio_path: str):
        """使用 PyAudio 播放音频"""
        audio = pyaudio.PyAudio()

        with wave.open(audio_path, "rb") as wf:
            stream = audio.open(
                format=audio.get_format_from_width(wf.getsampwidth()),
                channels=wf.getnchannels(),
                rate=wf.getframerate(),
                output=True
            )

            chunk_size = 1024
            data = wf.readframes(chunk_size)
            while data:
                stream.write(data)
                data = wf.readframes(chunk_size)

            stream.stop_stream()
            stream.close()

        audio.terminate()

    def _play_audio_powershell(self, audio_path: str):
        """使用 PowerShell SoundPlayer 播放音频"""
        import shutil

        # 1. 确保是真正的 WAV 格式
        wav_path = self._ensure_wav_format(audio_path)

        # 2. 复制到 Windows Temp 目录
        win_filename = f"wsl_tts_{int(time.time())}.wav"
        win_dest = f"/mnt/c/Users/sevnce/AppData/Local/Temp/{win_filename}"

        # 尝试多种路径复制
        copy_ok = False
        try:
            shutil.copy2(wav_path, win_dest)
            copy_ok = True
        except Exception:
            pass

        if not copy_ok:
            # 尝试通过 wslpath 获取 Windows 路径后复制
            try:
                result = subprocess.run(["wslpath", "-w", wav_path], capture_output=True)
                win_src = result.stdout.decode("utf-8", errors="replace").strip()
                win_dest2 = f"C:\\Users\\sevnce\\AppData\\Local\\Temp\\{win_filename}"
                subprocess.run(["cmd.exe", "/c", "copy", win_src, win_dest2], capture_output=True)
                copy_ok = True
            except Exception:
                pass

        if not copy_ok:
            # 最后尝试直接用原始路径
            raise RuntimeError("无法复制音频文件到 Windows 目录")

        # 3. 用 PowerShell SoundPlayer 播放
        win_path = f"C:\\Users\\sevnce\\AppData\\Local\\Temp\\{win_filename}"
        ps_cmd = f'$player = New-Object System.Media.SoundPlayer "{win_path}"; $player.PlaySync()'
        result = subprocess.run(
            ["powershell.exe", "-Command", ps_cmd],
            capture_output=True, timeout=60
        )

        # 4. 清理临时文件
        try:
            os.remove(win_dest)
        except Exception:
            pass

        if result.returncode != 0:
            stderr = result.stderr.decode("utf-8", errors="replace")[:200]
            raise RuntimeError(f"PowerShell 播放失败: {stderr}")

    def _record_audio(self, output_path: str) -> bool:
        """录制音频，自动选择可用方案"""
        if PYAUDIO_AVAILABLE:
            try:
                return self._record_audio_pyaudio(output_path)
            except Exception as e:
                print(f"PyAudio 录音失败: {e}，尝试 PowerShell 方案")

        # 尝试 PowerShell 方案
        try:
            return self._record_audio_powershell(output_path)
        except Exception as e:
            print(f"PowerShell 录音也失败: {e}")
            return False

    def _play_audio(self, audio_path: str):
        """播放音频，自动选择可用方案"""
        # 确保是真正的 WAV 格式
        wav_path = self._ensure_wav_format(audio_path)

        # 优先使用 PowerShell SoundPlayer（最可靠）
        try:
            self._play_audio_powershell(wav_path)
            return
        except Exception as e:
            print(f"  [调试] PowerShell 播放失败: {e}")

        # 备选：ffmpeg 播放
        if self._check_ffmpeg():
            try:
                self._play_audio_ffmpeg(wav_path)
                return
            except Exception as e:
                print(f"  [调试] ffmpeg 播放失败: {e}")

        # 最后尝试 PyAudio
        if PYAUDIO_AVAILABLE:
            try:
                self._play_audio_pyaudio(wav_path)
                return
            except Exception as e:
                print(f"  [调试] PyAudio 播放失败: {e}")

        print("  ⚠️ 所有播放方式都失败")

    @staticmethod
    def _ensure_wav_format(audio_path: str) -> str:
        """确保音频是 WAV 格式（检查文件头，MP3 需要转换）"""
        # 检查文件头：WAV 文件以 'RIFF' 开头，MP3 以 'ID3' 或 0xFF 开头
        try:
            with open(audio_path, 'rb') as f:
                header = f.read(4)
            # 已经是 WAV 格式
            if header[:4] == b'RIFF':
                return audio_path
        except Exception:
            pass

        # 需要转换格式
        wav_path = audio_path.rsplit('.', 1)[0] + '_converted.wav'
        if os.path.exists(wav_path):
            return wav_path

        try:
            subprocess.run(
                ['ffmpeg', '-y', '-i', audio_path, '-acodec', 'pcm_s16le', '-ar', '16000', '-ac', '1', wav_path],
                capture_output=True, timeout=15
            )
            if os.path.exists(wav_path):
                return wav_path
        except Exception:
            pass

        # 转换失败，返回原始路径
        return audio_path

    def _play_audio_ffmpeg(self, audio_path: str):
        """使用 ffmpeg 播放音频"""
        ffmpeg_path = self._find_ffmpeg()
        if not ffmpeg_path:
            return
        result = subprocess.run(
            ["wslpath", "-w", audio_path],
            capture_output=True
        )
        win_path = result.stdout.decode("utf-8", errors="replace").strip()
        ps_cmd = f"& '{ffmpeg_path}' -i '{win_path}' -autoexit -nodisp"
        subprocess.run(
            ["powershell.exe", "-Command", ps_cmd],
            capture_output=True, timeout=30
        )

    async def voice_mode(self):
        """语音对话模式"""
        if not PYAUDIO_AVAILABLE:
            print("⚠️ PyAudio 未安装，使用 Windows PowerShell 进行音频输入输出")

        print("\n" + "=" * 50)
        print("🎙️ 语音对话模式")
        print("=" * 50)
        print("对着麦克风说话，我会自动检测语音并回复")
        print("按 Ctrl+C 退出\n")

        while True:
            try:
                # 录音
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                wav_path = os.path.join(self.temp_dir, f"recording_{timestamp}.wav")

                if not self._record_audio(wav_path):
                    continue

                # ASR
                print("📝 识别中...")
                recognized_text = self.asr.transcribe(wav_path)
                print(f"📝 识别结果: {recognized_text}")

                if not recognized_text.strip():
                    print("未识别到有效内容，请重试")
                    continue

                # LLM
                print("🤖 思考中...")
                response_text = await self.llm_client.process_query(recognized_text)
                print(f"🤖 回复: {response_text}")

                # TTS
                tts_path = os.path.join(self.temp_dir, f"response_{timestamp}.wav")
                await self.tts.text_to_speech(response_text, tts_path)

                # 播放
                self._play_audio(tts_path)

                # 清理临时文件
                try:
                    os.remove(wav_path)
                    os.remove(tts_path)
                except Exception:
                    pass

            except KeyboardInterrupt:
                print("\n\n退出语音模式")
                break
            except Exception as e:
                print(f"错误: {e}")

    async def cli_mode(self):
        """命令行对话模式"""
        print("\n" + "=" * 50)
        print("💬 命令行对话模式")
        print("=" * 50)
        print("输入你的问题，输入 'quit' 或 'exit' 退出")
        print("输入 'voice' 切换到语音模式（如果可用）")
        print("输入 'tts' 开启/关闭语音回复\n")

        tts_enabled = True  # 默认开启语音回复

        while True:
            try:
                query = input("\n你: ").strip()

                if query.lower() in ("quit", "exit", "q"):
                    break

                if query.lower() == "voice":
                    await self.voice_mode()
                    continue

                if query.lower() == "tts":
                    tts_enabled = not tts_enabled
                    status = "开启" if tts_enabled else "关闭"
                    print(f"语音回复已{status}")
                    continue

                if not query:
                    continue

                print("🤖 思考中...")
                response = await self.llm_client.process_query(query)
                print(f"\n小智: {response}")

                # TTS 语音回复
                if tts_enabled:
                    try:
                        import tempfile
                        tts_path = os.path.join(tempfile.gettempdir(), f"cli_tts_{int(time.time())}.wav")
                        print("  🔊 正在合成语音...")
                        await self.tts.text_to_speech(response, tts_path)
                        print(f"  🔊 语音文件: {os.path.getsize(tts_path)} bytes")
                        print("  🔊 正在播放...")
                        self._play_audio(tts_path)
                        print("  🔊 播放完成")
                        try:
                            os.remove(tts_path)
                        except Exception:
                            pass
                    except Exception as e:
                        error_msg = str(e)
                        if '503' in error_msg:
                            print("  ⚠️ 语音合成服务暂时不可用")
                            print("    请稍后重试")
                        else:
                            print(f"  ⚠️ 语音播放失败: {error_msg[:150]}")

            except KeyboardInterrupt:
                print("\n\n退出命令行模式")
                break
            except Exception as e:
                print(f"错误: {e}")

    async def run(self, mode: str = "auto"):
        """运行客户端"""
        # 连接 MCP 服务器
        print("正在连接 MCP 服务器...")
        await self.llm_client.connect_all_default_servers()

        if not self.llm_client.sessions:
            print("❌ 未连接到任何 MCP 服务器，请检查配置")
            return

        print(f"✅ 已连接 {len(self.llm_client.sessions)} 个 MCP 服务器")

        if mode == "voice":
            await self.voice_mode()
        elif mode == "cli":
            await self.cli_mode()
        else:  # auto
            if PYAUDIO_AVAILABLE or self._check_ffmpeg():
                print("检测到音频能力，默认进入语音模式")
                print("（可通过 --cli 参数强制使用命令行模式）")
                await self.voice_mode()
            else:
                print("未检测到音频设备，使用命令行模式")
                await self.cli_mode()

    @staticmethod
    def _find_ffmpeg() -> str:
        """查找 ffmpeg 可执行文件路径"""
        # 先检查 PATH
        try:
            result = subprocess.run(
                ["where.exe", "ffmpeg.exe"],
                capture_output=True, timeout=5
            )
            if result.returncode == 0:
                return result.stdout.decode("utf-8", errors="replace").strip().split('\n')[0].strip()
        except Exception:
            pass

        # 使用 PowerShell 搜索常见安装路径
        search_patterns = [
            r"C:\ffmpeg\bin\ffmpeg.exe",
            r"C:\Program Files\ffmpeg\bin\ffmpeg.exe",
            r"C:\Program Files (x86)\ffmpeg\bin\ffmpeg.exe",
            r"C:\Program Files (x86)\Lenovo\LegionZone\*\SEGamingAI\services\editor\ffmpeg.exe",
        ]
        for pattern in search_patterns:
            result = subprocess.run(
                ["powershell.exe", "-Command",
                 f"Get-ChildItem -Path '{pattern}' -ErrorAction SilentlyContinue | Select-Object -First 1 -ExpandProperty FullName"],
                capture_output=True, timeout=10
            )
            if result.returncode == 0:
                path = result.stdout.decode("utf-8", errors="replace").strip()
                if path:
                    return path

        # 全盘搜索
        result = subprocess.run(
            ["powershell.exe", "-Command",
             "Get-ChildItem -Path 'C:\\' -Filter 'ffmpeg.exe' -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1 -ExpandProperty FullName"],
            capture_output=True, timeout=30
        )
        if result.returncode == 0:
            path = result.stdout.decode("utf-8", errors="replace").strip()
            if path:
                return path

        return ""

    @staticmethod
    def _check_ffmpeg() -> bool:
        """检查是否有可用的 ffmpeg"""
        return bool(LocalClient._find_ffmpeg())

    async def cleanup(self):
        """清理资源"""
        await self.llm_client.cleanup()
        # 清理临时目录
        import shutil
        try:
            shutil.rmtree(self.temp_dir, ignore_errors=True)
        except Exception:
            pass


def main():
    parser = argparse.ArgumentParser(description="本地 LLM + MCP 客户端")
    parser.add_argument("--config", "-c", default="mcp_config.json",
                        help="MCP 服务器配置文件路径")
    parser.add_argument("--mode", "-m", choices=["auto", "voice", "cli"], default="auto",
                        help="运行模式: auto(自动), voice(语音), cli(命令行)")
    parser.add_argument("--cli", action="store_true", help="快捷方式：命令行模式")
    parser.add_argument("--voice", action="store_true", help="快捷方式：语音模式")
    parser.add_argument("--server", "-s", action="append", metavar="NAME",
                        help="指定要连接的 MCP 服务器名称")
    args = parser.parse_args()

    # 快捷参数处理
    if args.cli:
        args.mode = "cli"
    elif args.voice:
        args.mode = "voice"

    # 加载系统提示词
    system_prompt = None
    prompt_path = os.path.join(os.path.dirname(__file__), "system_prompt.md")
    if os.path.exists(prompt_path):
        with open(prompt_path, "r", encoding="utf-8") as f:
            system_prompt = f.read()

    client = LocalClient(config_path=args.config, system_prompt=system_prompt)

    try:
        async def run():
            if args.server:
                for server_name in args.server:
                    await client.llm_client.connect_to_server(server_name)
                if not client.llm_client.sessions:
                    print("❌ 未连接到任何指定的 MCP 服务器")
                    return
            await client.run(mode=args.mode)

        asyncio.run(run())
    except KeyboardInterrupt:
        print("\n\n已停止")
    finally:
        asyncio.run(client.cleanup())


if __name__ == "__main__":
    main()
