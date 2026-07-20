import os
import platform
from funasr import AutoModel
from funasr.utils.postprocess_utils import rich_transcription_postprocess
from dotenv import load_dotenv


load_dotenv()

# 检测是否在 WSL 环境中
def _is_wsl():
    if platform.system() == "Linux":
        try:
            with open("/proc/version", "r") as f:
                ver = f.read().lower()
                return "microsoft" in ver or "wsl" in ver
        except Exception:
            pass
    return False

class AudioToText:
    def __init__(self, model_dir=None):
        if model_dir is None:
            model_dir = os.getenv("ASR_MODEL_DIR", "./models/SenseVoiceSmall")

        # 转换为绝对路径（FunASR 需要绝对路径加载本地模型）
        self.model_dir = os.path.abspath(model_dir)

        # 如果路径不存在，尝试向上查找（兼容从 server/ 子目录运行的情况）
        if not os.path.exists(self.model_dir):
            # 尝试项目根目录下的 models/
            alt_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../models/SenseVoiceSmall"))
            if os.path.exists(alt_path):
                self.model_dir = alt_path

        # 自动选择设备
        device = self._auto_select_device()
        print(f"ASR 使用设备: {device}")
        print(f"ASR 模型路径: {self.model_dir}")

        self.model = AutoModel(
                model=self.model_dir,
                vad_model="fsmn-vad",
                vad_kwargs={"max_single_segment_time": 30000},
                device=device,
                disable_update=True,
        )

    @staticmethod
    def _auto_select_device() -> str:
        """自动选择计算设备"""
        # 检查是否有 CUDA
        try:
            import torch
            if torch.cuda.is_available():
                return "cuda:0"
        except ImportError:
            pass

        # 检查是否有 MPS (Apple Silicon)
        try:
            import torch
            if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
                return "mps"
        except (ImportError, AttributeError):
            pass

        return "cpu"

    def transcribe(self, audio_path, language="auto", use_itn=True, batch_size_s=60, merge_vad=True, merge_length_s=15):
        """
        audio_path: 音频文件路径
        返回：识别到的文本字符串
        """
        res = self.model.generate(
            input=audio_path,
            cache={},
            language=language,
            use_itn=use_itn,
            batch_size_s=batch_size_s,
            merge_vad=merge_vad,
            merge_length_s=merge_length_s,
        )
        text = rich_transcription_postprocess(res[0]["text"])
        return text


if __name__ == "__main__":
    audio_file = "output.wav"  # 修改为你的音频文件
    at = AudioToText()
    text = at.transcribe(audio_file)
    print("识别结果：", text)
