# 安装、硬件与 ASR 配置

下面三种源码环境的名称都为 `vsummary`。每台机器只创建其中一种环境，之后使用对应启动脚本即可。
> 该示例演示settings.toml配置方法，实际也可以进入前端网站后去前端可视化配置

## Windows + NVIDIA 显卡

### Windows 整合包

整合包目前仅提供 Windows。下载 [GitHub Releases](https://github.com/alpha03123/vsummary/releases) 的 GPU 版，解压后配置模型供应商并双击 `start.bat`。

### 源码版

```powershell
git clone <repo-url> vsummary
cd vsummary
conda env create -f environment.yml
conda activate vsummary
cd src/frontend
npm install
cd ../..
start.bat
```

`config/settings.toml`：

```toml
[asr]
provider = "faster_whisper"

[asr.faster_whisper]
device = "gpu"
compute_type = "float16"

[agent_retrieval]
embedding_device = "gpu"
```

视频转写和 FastEmbed embedding 都使用 CUDA。

## Windows + AMD 显卡

源码版使用 CPU Python 环境，转写 GPU 加速交给 Vulkan 版 `whisper-cli`：

```powershell
git clone <repo-url> vsummary
cd vsummary
conda env create -f environment.cpu.yml
conda activate vsummary
cd src/frontend
npm install
cd ../..
start.bat
```

构建 Vulkan 版 `whisper-cli`：

```powershell
git clone https://github.com/ggml-org/whisper.cpp
cd whisper.cpp
cmake -B build -DGGML_VULKAN=1
cmake --build build --config Release
```

将生成的 `whisper-cli.exe` 加入 PATH。可用 `where whisper-cli` 验证；找不到时，将绝对路径写入配置：

```toml
[asr]
provider = "whisper_cpp"

[asr.whisper_cpp]
binary_path = "C:/path/to/whisper-cli.exe"
model = "large-v3-turbo-q5_0"

[agent_retrieval]
embedding_device = "cpu"
```

## macOS / Apple Silicon

```bash
git clone <repo-url> vsummary
cd vsummary
conda env create -f environment.cpu.yml
conda activate vsummary
cd src/frontend
npm install
cd ../..
chmod +x start.command
./start.command
```

`start.command` 自动找到 `vsummary` 环境的 Python，分别在后台启动后端与前端，并打开浏览器。

仅 CPU 转写时：

```toml
[asr]
provider = "faster_whisper"

[asr.faster_whisper]
device = "cpu"
compute_type = "int8"

[agent_retrieval]
embedding_device = "cpu"
```

需要 GPU 转写时，构建 Metal 版 whisper.cpp：

```bash
git clone https://github.com/ggml-org/whisper.cpp
cd whisper.cpp
cmake -B build
cmake --build build --config Release
```

配置 `whisper_cpp`：

```toml
[asr]
provider = "whisper_cpp"

[asr.whisper_cpp]
binary_path = "/Users/you/path/to/whisper-cli"
model = "large-v3-turbo-q5_0"

[agent_retrieval]
embedding_device = "cpu"
```

## 不想配置本地 ASR

如果本地模型下载、显卡环境或编译 `whisper.cpp` 的操作较麻烦，推荐使用阿里云百炼的云端 ASR。它不需要下载本地转写模型，也不依赖本机 GPU

在百炼控制台创建 API Key 后，将它写入项目根目录的 `.env`：

```dotenv
DASHSCOPE_API_KEY=你的百炼_API_Key
```

然后在 `config/settings.toml` 中选择云端转写器：

```toml
[asr]
provider = "aliyun_bailian"

[asr.aliyun_bailian]
base_url = "https://dashscope.aliyuncs.com"
model = "paraformer-v2"
```

保存后重新启动应用即可。LLM 的 `OPENAI_*` 配置仍然必需，云端 ASR 只负责生成视频转写文本。

## whisper.cpp 模型

`faster_whisper` 使用 CTranslate2 模型，放在 `data/models/faster-whisper/<模型 ID>/`，至少包含 `model.bin` 与 `config.json`。

`whisper_cpp` 使用 GGML 模型，两者不能互用。设置页选择“本地 whisper.cpp”后可直接下载；也可手动下载 [ggerganov/whisper.cpp](https://huggingface.co/ggerganov/whisper.cpp) 的模型。默认模型位置：

```text
data/models/whisper-cpp/large-v3-turbo-q5_0/ggml-large-v3-turbo-q5_0.bin
```

## 公共配置

复制 `.env.example` 为 `.env`，填写 LLM：

```dotenv
OPENAI_API_KEY=sk-你的密钥
OPENAI_PROVIDER=openai_compatible
OPENAI_BASE_URL=https://api.deepseek.com
OPENAI_MODEL=deepseek-v4-flash
```

无法稳定访问 Hugging Face 时，在 `.env` 增加：

```dotenv
HF_ENDPOINT=https://hf-mirror.com
```
