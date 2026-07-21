#!/usr/bin/env python3
"""ChatTTS 离线情感语音合成"""

import os
import json
import hashlib

import numpy as np


class ChatTTS:
    """ChatTTS 离线情感 TTS"""

    def __init__(self, config=None):
        self.config = config or {}
        self.model_path = self.config.get('model_path', '')
        self.temp_dir = self.config.get('temp_dir', '/tmp/chattts')
        os.makedirs(self.temp_dir, exist_ok=True)
        self._chat = None  # 懒加载
        # 默认使用女声种子（通过 sample_random_speaker 生成后固定）
        self._female_spk = None

    @property
    def chat(self):
        """懒加载 ChatTTS 模型"""
        if self._chat is None:
            import ChatTTS
            self._chat = ChatTTS.Chat()
            if self.model_path and os.path.exists(self.model_path):
                self._chat.load(source="local", custom_path=self.model_path)
            else:
                self._chat.load(compile=False)
        return self._chat

    async def text_to_speech(self, text, output_file):
        """合成语音"""
        import ChatTTS
        import torch

        # 情感参数
        params = self.config.get('params', {})
        temperature = params.get('temperature', 0.5)
        top_p = params.get('top_p', 0.7)
        top_k = params.get('top_k', 20)

        # 使用固定女声（首次生成后缓存）
        if self._female_spk is None:
            import torch
            torch.manual_seed(2)  # 固定种子生成女声
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

        # 保存音频（使用 scipy 避免 torchcodec 依赖）
        import scipy.io.wavfile as wavfile
        audio_data = wavs[0]
        if isinstance(audio_data, torch.Tensor):
            audio_data = audio_data.cpu().numpy()
        # 归一化到 16-bit 范围
        audio_data = (audio_data * 32767).astype('int16')
        wavfile.write(output_file, 24000, audio_data)

        return output_file


if __name__ == "__main__":
    tts = ChatTTS()
    print("正在加载 ChatTTS 模型（首次需要下载，约 500MB）...")
    tts.text_to_speech_sync("你好，我是 ChatTTS 语音合成测试", "/tmp/chattts_test.wav")
    print("合成完成: /tmp/chattts_test.wav")
