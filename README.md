# vsummary

一个本地视频知识库工具。把视频放进来，自动转写成文字、生成 AI 概况，然后可以对着视频内容提问、做笔记、生成思维导图和知识卡片。

---

## 核心特性

- **完全本地化转写**：使用 `faster-whisper` 在本地进行视频转写，隐私安全，无需消耗 API 流量。
- **AI 知识增强**：基于转写文本生成思维导图、知识卡片和多维度的 AI 总结。
- **对话式检索**：直接对着视频库提问，系统会根据视频内容精准定位并回答。
- **B 站合集导入**：支持一键解析并下载 Bilibili 合集视频。

---

## 准备环境

在启动之前，请确保已安装以下工具：

| 工具 | 用途 | 下载地址 |
|------|------|----------|
| Miniconda 或 Anaconda | 管理 Python 环境和依赖 | https://www.anaconda.com/download/success |
| Node.js 18+ | 运行前端界面 | https://nodejs.org |


---

## 快速开始

### 1. 创建 Conda 环境

**使用 Miniconda(推荐) 的用户**，打开 Anaconda Prompt 或终端，在项目根目录下执行：

```bat
conda env create -f environment.yml
conda activate vsummary
```

**已安装 Anaconda 的用户**，操作完全相同——打开 Anaconda Prompt（或 Anaconda Navigator 内的终端），在项目根目录下执行相同命令即可：

```bat
conda env create -f environment.yml
conda activate vsummary
```

这会自动安装 Python 3.11、FFmpeg 及所有后端依赖，无需额外配置环境变量。

### 2. （可选）启用 GPU 加速

若你有 **NVIDIA 显卡**，Conda 环境已经默认安装了所需的 CUDA 运行库。

只需修改 `config/settings.toml`（初次运行后自动生成），将 `device` 改为 `"cuda"` 即可：

```toml
[asr.faster_whisper]
device = "cuda"
```

### 3. 安装前端依赖

```bat
cd src\frontend
npm install
cd ..\..
```

### 4. 配置说明

项目包含两个核心配置文件：

#### A. 密钥配置 (`.env`)

复制并重命名 `.env.example` 为 `.env`，填入你的 AI 模型信息：

```dotenv
OPENAI_API_KEY=sk-你的密钥
OPENAI_PROVIDER=openai_compatible
OPENAI_BASE_URL=https://你的供应商地址/v1
OPENAI_MODEL=gpt-4o
```

#### B. 运行配置 (`config/settings.toml`)

初次运行后自动生成，可调整以下参数：

- **转写设备**：`device = "cpu"`（默认）或 `"cuda"`（GPU 加速）
- **模型大小**：默认为 `large-v3-turbo`（约 1.5GB），配置较低可改为 `small` 或 `base`

### 5. 启动服务

分别打开两个终端窗口执行：

**终端 1 — 启动后端：**

```bat
conda activate vsummary
cd src
python -m uvicorn backend.api.app:app --host 127.0.0.1 --port 8001
```

**终端 2 — 启动前端：**

```bat
cd src\frontend
npm run dev
```

启动后，访问浏览器：**[http://127.0.0.1:4173](http://127.0.0.1:4173)**

 ## **一键启动**：
 直接双击根目录下的 `start.bat`，会自动打开两个终端窗口分别运行后端和前端。



## 数据

- **视频文件**：放在 `videos/` 目录下。
- **处理结果**：所有的转写、总结、笔记都存储在 `workspace/` 目录下。
- **本地模型**：自动下载的模型文件存储在 `data/models/` 目录下。
- **隐私说明**：除了向 LLM 提供商发送文本进行总结/对话外，所有音频处理和原始数据均保留在本地。

---

## 常见问题

**Q: 出现 `cublas.dll not found` 或 `cudnn` 相关报错？**

A: 按照上方"启用 GPU 加速"步骤安装 CUDA 运行库，或将 `config/settings.toml` 中的 `device` 改回 `"cpu"` 以纯 CPU 运行。

**Q: 第一次运行生成概况很慢？**

A: 首次运行需要下载约 1.5GB 的转写模型，取决于网速。下载完成后，后续转写速度将大幅提升。

**Q: 前端页面显示"连接后端失败"？**

A: 请检查后端终端窗口是否有红色报错。通常是因为端口 8001 被占用或 `.env` 里的 API Key 格式不正确。

**Q: 如何更换转写语言？**

A: 修改 `config/settings.toml` 中的 `language = "zh"` 为你需要的语言代码。
