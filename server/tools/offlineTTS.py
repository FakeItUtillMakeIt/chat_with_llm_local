#!/usr/bin/env python3
"""离线 TTS 工具 - 使用 Windows SAPI（通过 PowerShell）"""

import os
import subprocess
import tempfile


class OfflineTTS:
    """离线语音合成（使用 Windows 内置 SAPI）"""

    def __init__(self, config=None):
        self.config = config or {}
        self.rate = self.config.get('rate', 0)  # -10 到 10
        self.volume = self.config.get('volume', 100)  # 0 到 100

    def _get_voices(self):
        """获取所有可用语音"""
        ps_cmd = '''
Add-Type -AssemblyName System.Speech
$synth = New-Object System.Speech.Synthesis.SpeechSynthesizer
$voices = $synth.GetInstalledVoices()
foreach ($v in $voices) {
    $info = $v.VoiceInfo
    Write-Output "$($info.Name)|$($info.Culture)|$($info.Gender)"
}
'''
        result = subprocess.run(
            ["powershell.exe", "-Command", ps_cmd],
            capture_output=True, text=True, timeout=10
        )
        voices = []
        for line in result.stdout.strip().split('\n'):
            parts = line.strip().split('|')
            if len(parts) >= 2:
                voices.append({'name': parts[0], 'culture': parts[1]})
        return voices

    async def text_to_speech(self, text, output_file):
        """合成语音并保存到文件"""
        # 使用 Windows SAPI 合成语音
        ps_cmd = f'''
Add-Type -AssemblyName System.Speech
$synth = New-Object System.Speech.Synthesis.SpeechSynthesizer
$synth.Rate = {self.rate}
$synth.Volume = {self.volume}
$synth.SetOutputToWaveFile("{output_file}")
$synth.Speak("{text}")
$synth.SetOutputToDefaultAudioDevice()
'''
        result = subprocess.run(
            ["powershell.exe", "-Command", ps_cmd],
            capture_output=True, text=True, timeout=30
        )

        if result.returncode != 0:
            raise RuntimeError(f"TTS 合成失败: {result.stderr[:200]}")

        return output_file

    def text_to_speech_sync(self, text, output_file):
        """同步合成语音"""
        import asyncio
        return asyncio.run(self.text_to_speech(text, output_file))


if __name__ == "__main__":
    tts = OfflineTTS()
    print("可用语音:")
    for v in tts._get_voices():
        print(f"  - {v['name']} ({v['culture']})")

    print("\n合成测试...")
    asyncio.run(tts.text_to_speech("你好，这是离线语音合成测试", "/tmp/offline_tts_test.wav"))
    print("合成完成: /tmp/offline_tts_test.wav")
