#!/usr/bin/env python3
"""ChatTTS 离线情感语音合成"""

import os
import json
import hashlib
import time

import numpy as np


class ChatTTS:
    """ChatTTS 离线情感 TTS"""

    def __init__(self, config=None):
        self.config = config or {}
        self.model_path = self.config.get('model_path', '')
        self.temp_dir = self.config.get('temp_dir', '/tmp/chattts')
        os.makedirs(self.temp_dir, exist_ok=True)
        self._chat = None
        self._female_spk = None
        # 预热：立即加载模型
        self._warmup()

    def _warmup(self):
        """预热模型（加载到 GPU）"""
        import ChatTTS
        import torch

        self._chat = ChatTTS.Chat()

        # 强制使用 GPU（如果可用）
        if torch.cuda.is_available():
            self._chat.device = torch.device("cuda")
            print("[ChatTTS] 使用 CUDA 加速")
        else:
            print("[ChatTTS] 使用 CPU 推理")

        if self.model_path and os.path.exists(self.model_path):
            self._chat.load(source="local", custom_path=self.model_path)
        else:
            self._chat.load(compile=False)

        # 预热推理（第一次推理较慢）
        torch.manual_seed(2)  #种子 2 通常产生较柔和的音色
        spk = self._chat.sample_random_speaker()
        self._female_spk = spk
        # 执行一次短推理预热
        self._chat.infer(["预热"], params_infer_code=ChatTTS.Chat.InferCodeParams(
            spk_emb=spk, temperature=0.1, top_P=0.5, top_K=10
        ))

    @property
    def chat(self):
        """获取 ChatTTS 模型"""
        if self._chat is None:
            self._warmup()
        return self._chat

    async def text_to_speech(self, text, output_file):
        """合成语音"""
        import ChatTTS
        import torch

        start = time.time()

        # 情感参数
        params = self.config.get('params', {})
        temperature = params.get('temperature', 0.3)
        top_p = params.get('top_p', 0.7)
        top_k = params.get('top_k', 20)

        # 使用固定音色
        if self._female_spk is None:
            torch.manual_seed(42)
            self._female_spk = self.chat.sample_random_speaker()

        params_infer_code = ChatTTS.Chat.InferCodeParams(
            spk_emb=self._female_spk,
            temperature=temperature,
            top_P=top_p,
            top_K=top_k,
        )

        # 生成语音
        wavs = self.chat.infer(
            [text],
            params_infer_code=params_infer_code,
        )

        # 保存音频
        import scipy.io.wavfile as wavfile
        audio_data = wavs[0]
        if isinstance(audio_data, torch.Tensor):
            audio_data = audio_data.cpu().numpy()
        audio_data = (audio_data * 32767).astype('int16')
        wavfile.write(output_file, 24000, audio_data)

        return output_file


if __name__ == "__main__":
    tts = ChatTTS()
    print("正在加载 ChatTTS 模型...")
    tts.text_to_speech("你好，我是 ChatTTS 语音合成测试", "/tmp/chattts_test.wav")
    print("合成完成: /tmp/chattts_test.wav")
