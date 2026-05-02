# vsummary

一个本地视频知识库工具。把视频放进来，自动转写为文本、生成 AI 概况，然后可以基于视频内容进行问答、做笔记、生成思维导图和知识卡片。


---

## 核心特性

- **本地转写**：使用 `faster-whisper` 在本地执行视频转写。
- **AI 知识增强**：基于转写结果生成 AI 概况、思维导图、知识卡片与笔记。
- **对话式检索**：直接围绕视频内容发问，系统会定位并回答。

---

## 准备环境

启动前请先准备：

| 工具 | 用途 | 下载地址 |
|------|------|----------|
| Miniconda 或 Anaconda | 管理 Python 环境和依赖 | https://www.anaconda.com/download/success |
| Node.js 18+ | 运行前端界面 | https://nodejs.org |

推荐使用 **Miniconda/Anaconda Prompt** 进行初始化与启动。

---

## 快速开始

### 1. 创建 Conda 环境

在项目根目录执行：

```bat
conda env create -f environment.yml
conda activate vsummary
```

这会自动安装：

- Python 3.11
- FFmpeg
- 后端依赖
- `faster-whisper` 所需的 CUDA 12 运行时包

### 2. 安装前端依赖

```bat
cd src\frontend
npm install
cd ..\..
```

### 3. 准备本地视频

将你要处理的视频文件放到本地后，通过前端界面的：

- `添加系列`
- `添加视频`
- `添加 Playground 视频`

进行本地导入。

### 4. 复制 `.env`

复制 `.env.example` 为 `.env`，再填写模型供应商配置：

```dotenv
OPENAI_API_KEY=sk-你的密钥
OPENAI_PROVIDER=openai_compatible
OPENAI_BASE_URL=https://api.deepseek.com
OPENAI_MODEL=deepseek-v4-flash
```

说明：

- `OPENAI_BASE_URL` 可以写成：
  - `https://api.deepseek.com`
  - `https://api.deepseek.com/v1`
- 程序会自动补齐并归一为 `/v1`
- 最终实际请求由后端统一拼到 `chat/completions`

### 5. 配置 HuggingFace 镜像

如果你所在网络环境无法稳定访问 HuggingFace，请在 `.env` 里继续加入：

```dotenv
HF_ENDPOINT=https://hf-mirror.com
```



### 6. 首次启动后检查 `config/settings.toml`

程序第一次运行后会生成 `config/settings.toml`。推荐重点检查这两段：

```toml
[asr.faster_whisper]
device = "auto"
model_size = "large-v3-turbo"
compute_type = "float16"
transcription_mode = "accurate"

[agent_retrieval]
embedding_provider = "local_huggingface"
embedding_model = "BAAI/bge-base-zh-v1.5"
embedding_device = "cpu"
embedding_batch_size = 8
```

说明：

- `device` 控制 **视频转写（fast whisper模型）** 用 CPU 还是 NVIDIA GPU（建议GPU）
- `embedding_device` 控制 **RAG 向量检索模型** 用 CPU 还是 GPU (建议CPU)

### 7. 启动服务

#### 方式 A：一键启动

直接双击根目录下的 `start.bat`。

#### 方式 B：手动启动

**终端 1：后端**

```bat
cd src
conda run -n vsummary python -m uvicorn backend.api.app:app --host 127.0.0.1 --port 8001
```

**终端 2：前端**

```bat
cd src\frontend
npm run dev
```

启动后访问：

- 前端：[http://127.0.0.1:4173](http://127.0.0.1:4173)
- 后端：[http://127.0.0.1:8001](http://127.0.0.1:8001)

---

## GPU 说明

### 视频转写 GPU

如果你有 NVIDIA 显卡，并且希望启用视频转写 GPU 加速，可以：

```toml
[asr.faster_whisper]
device = "gpu"
```

### CUDA 11 用户


如果你的机器仍然停留在 CUDA 11，建议：

1. 优先使用 CPU 模式
2. 或尝试把 `environment.yml` 中默认的 CUDA 12 运行时包改成 CUDA 11 对应包
```yaml
- nvidia-cublas-cu11
- nvidia-cudnn-cu11
- nvidia-cuda-runtime-cu11
- nvidia-cuda-nvrtc-cu11
```


### RAG / embedding GPU

`embedding_device` 默认建议保持为：

```toml
embedding_device = "cpu"
```
- 当前环境变量配置的是cpu的torch，如果你自己安装了GPU TORCH，可以改为GPU.


---

## 数据目录

- `videos/`：原始视频文件
- `workspace/`：转写、概况、笔记等工作产物
- `data/models/`：本地模型文件

除了发给 LLM 供应商的文本请求外，原始音视频处理都保留在本地。

---

## 常见问题

### 1. `cublas.dll not found` / `cudart64_12.dll` / `cudnn` 报错

说明当前 GPU 运行时没有就绪。

建议顺序：

1. 确认你是通过 `environment.yml` 创建环境
2. 确认后端是从这个环境启动的
3. 如果还不行，先改回 CPU：

```toml
[asr.faster_whisper]
device = "cpu"
```

### 2. 只有 CUDA 11

当前默认环境走的是 **CUDA 12**。如果你必须使用 CUDA 11，可以尝试把 `environment.yml` 中的以下依赖改为 CUDA 11 对应包：

```yaml
- nvidia-cublas-cu11
- nvidia-cudnn-cu11
- nvidia-cuda-runtime-cu11
- nvidia-cuda-nvrtc-cu11
```


### 3. HuggingFace 下载很慢 / 失败

在 `.env` 中加入：

```dotenv
HF_ENDPOINT=https://hf-mirror.com
```

然后重启后端。

### 4. RAG 报 `Torch not compiled with CUDA enabled`

说明你把 embedding 设备设成了 GPU，但当前 PyTorch 不是 CUDA 版。

请改回：

```toml
[agent_retrieval]
embedding_device = "cpu"
```


### 5. 如何更换转写语言

修改：

```toml
[asr]
language = "zh"
```

改成你需要的语言代码即可。
