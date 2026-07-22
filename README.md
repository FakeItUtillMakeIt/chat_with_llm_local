# Chat with LLM - 本地智能语音助手

基于 LLM + MCP 的本地智能语音助手，支持离线语音合成、企业微信接入、文件操作等功能。

## 功能特性

- 🎙️ **语音对话**：离线语音识别 (FunASR) + 情感语音合成 (ChatTTS)
- 💬 **命令行对话**：文字交互，同时支持语音回复
- 🔧 **MCP 工具扩展**：
  - 文本编辑器：读写文件、目录浏览
  - 屏幕亮度控制：获取/设置亮度
  - 企业微信：消息收发（支持内网穿透）
- 🔌 **大模型支持**：兼容 OpenAI API 协议（默认 Longcat）
- 🏠 **完全离线**：TTS/ASR 均支持本地运行

## 项目结构

```
chat_with_llm_local/
├── server/
│   ├── llm_mcp.py              # MCP 客户端 + LLM 交互
│   ├── local_client.py         # 本地交互入口（语音/命令行）
│   ├── mcp_config.json         # MCP 服务器配置
│   ├── system_prompt.md        # LLM 系统提示词
│   ├── .env.example            # 环境变量模板
│   ├── mcp-server/
│   │   ├── text-editor/        # 文本编辑器 MCP 工具
│   │   ├── display/            # 屏幕亮度 MCP 工具
│   │   └── wecom/              # 企业微信 MCP 工具
│   └── tools/
│       ├── audio_to_text.py    # 离线语音识别 (FunASR)
│       ├── offlineTTS.py       # 离线语音合成 (Windows SAPI)
│       └── chatTTS.py          # 情感语音合成 (ChatTTS)
├── scripts/
│   ├── start-wecom-tmux.sh     # 企业微信一键启动（tmux）
│   ├── run-wecom-mcp.sh        # 企业微信 MCP 服务器
│   ├── run-serveo.sh           # serveo 内网穿透
│   └── test-wecom-callback.sh  # 回调 URL 测试
├── models/                     # ASR 模型文件
│   └── SenseVoiceSmall/        # SenseVoice 语音识别模型（huggingface下载）#https://huggingface.co/FunAudioLLM/SenseVoiceSmall #https://github.com/FunAudioLLM/SenseVoice
├── asset/                      # ChatTTS 模型文件（自动下载）
└── 企业微信接入指南.md           # 企业微信配置文档
│── requirements.txt        # Python 依赖
├── README.md
```

## 快速开始

### 1. 环境准备

```bash
# 创建 conda 环境
conda create -n chat_with_llm python=3.10 -y
conda activate chat_with_llm

# 安装依赖
cd server
pip install -r requirements.txt
```

### 2. 下载 ASR 模型

将 SenseVoiceSmall 模型文件放入 `models/` 目录：

```bash
# 从 HuggingFace 下载
# https://huggingface.co/FunAudioLLM/SenseVoiceSmall
```

### 3. 配置环境变量

```bash
cp .env.example .env
# 编辑 .env 填入你的 API Key
```

```env
LLM_API_KEY=your_api_key
LLM_BASE_URL=https://api.longcat.chat/openai/v1
LLM_MODEL=LongCat-2.0
ASR_MODEL_DIR=./models/SenseVoiceSmall
```

### 4. 启动使用

```bash
cd server

# 命令行模式（带语音回复）
python local_client.py --cli

# 语音对话模式
python local_client.py --voice
```

## 命令行参数

| 参数 | 说明 |
|------|------|
| `--cli` | 命令行模式 |
| `--voice` | 语音对话模式 |
| `--config`, `-c` | MCP 配置文件路径 |
| `--server`, `-s` | 指定 MCP 服务器名称 |

## 交互命令

在 CLI 模式下：

| 输入 | 功能 |
|------|------|
| `tts` | 开启/关闭语音回复 |
| `voice` | 切换到语音对话模式 |
| `quit` / `exit` | 退出 |

## MCP 工具

### 文本编辑器

- `read_file(path)` - 读取文件内容
- `write_file(path, content)` - 写入文件（覆盖）
- `append_file(path, content)` - 追加内容
- `open_in_editor(path)` - 用系统编辑器打开
- `list_directory(path)` - 列出目录内容

### 屏幕亮度

- `get_brightness()` - 获取当前亮度
- `set_brightness(percent)` - 设置亮度 (0-100)

### 企业微信（可选）

- `send_message(user_id, content)` - 发送文本消息
- `send_markdown(user_id, content)` - 发送 Markdown 消息
- `send_group_message(chat_id, content)` - 发送群消息
- `get_unread_messages()` - 获取未读消息
- `get_status()` - 获取连接状态

## 企业微信接入

详见 [企业微信接入指南.md](企业微信接入指南.md)

核心步骤：
1. 注册企业微信并创建自建应用
2. 配置 .env 中的企业微信参数
3. 使用 serveo 内网穿透暴露本地服务
4. 在企业微信后台设置回调 URL

## 语音合成配置

### ChatTTS（默认）

ChatTTS 支持情感化语音合成，首次使用需下载模型（约 500MB）。

```python
# 在 chatTTS.py 中配置
tts = ChatTTS({
    "temperature": 0.3,  # 温度（影响情感表达）
    "top_p": 0.7,        # 采样参数
    "top_k": 20,         # 采样参数
})
```

### 切换音色

ChatTTS 通过随机种子控制音色。运行以下脚本生成不同音色样本：

```bash
python tools/chatTTS.py
```

## 系统要求

- Python 3.10+
- CUDA（推荐，用于 ASR 和 TTS 加速）
- Windows（使用 WSL）：语音播放依赖 Windows API
- 麦克风（语音模式）

## 常见问题

**Q: TTS 没有声音？**
A: 检查 Windows 端音频设备；确认 ffmpeg 可用（用于格式转换）。

**Q: ASR 模型加载失败？**
A: 确认 SenseVoiceSmall 模型文件完整下载；检查 CUDA 是否可用。

**Q: 企业微信回调无法访问？**
A: 检查 serveo 是否正常运行；确认回调 URL 正确配置。

## License

MIT
