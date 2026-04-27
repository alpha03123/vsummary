# vsummary

一个本地视频知识库工具。把视频放进来，自动转写成文字、生成 AI 概况，然后可以对着视频内容提问、做笔记、生成思维导图和知识卡片。

---

## 核心特性

- **完全本地化转写**：使用 `faster-whisper` 在本地进行视频转写，隐私安全，无需消耗 API 流量。
- **AI 知识增强**：基于转写文本生成思维导图、知识卡片和多维度的 AI 总结。
- **对话式检索**：直接对着视频库提问，系统会根据视频内容精准定位并回答。
- **B 站合集导入**：支持一键解析并下载 Bilibili 合集视频。

---

##  准备环境

在启动之前，请确保已安装以下工具：

| 工具 | 用途 | 下载地址 |
|------|------|----------|
| Python 3.11 | 运行后端服务 | https://python.org |
| Node.js 18+ | 运行前端界面 | https://nodejs.org |
| FFmpeg | 视频音频提取 | https://ffmpeg.org（需加入系统 PATH） |


---

##  快速开始

### 1. 安装依赖

在项目根目录下执行：

```bat
# 创建并激活虚拟环境
python -m venv .venv
.venv\Scripts\activate

# 安装后端依赖 (包含 yt-dlp, faster-whisper 等)
pip install -r requirements.txt

# 安装前端依赖
cd src\frontend
npm install
cd ..\..
```

### 2. 配置说明

项目包含两个核心配置文件：

#### A. 密钥配置 (`.env`)
复制并重命名 `.env.example` 为 `.env`，填入你的 AI 模型信息（用于对话和总结）：
```dotenv
OPENAI_API_KEY=sk-你的密钥
OPENAI_PROVIDER=openai_compatible
OPENAI_BASE_URL=https://你的供应商地址/v1
OPENAI_MODEL=gpt-4o
```

#### B. 运行配置 (`config/settings.toml`)
该文件控制本地转写模型的行为（初次运行会自动生成默认配置）：
- **GPU 加速**：若有 NVIDIA 显卡，将 `[asr.faster_whisper]` 下的 `device` 改为 `"cuda"`。
- **模型大小**：默认为 `large-v3-turbo`（约 1.5GB），若配置较低可改为 `small` 或 `base`。

### 3. 一键启动

直接双击根目录下的 `start.bat`。

启动后，访问浏览器：**[http://127.0.0.1:4173](http://127.0.0.1:4173)**

---

## 手动启动方法 

如果 `start.bat` 无法运行，请分别在两个终端执行：

**启动后端：**
```bat
.venv\Scripts\activate
cd src
python -m uvicorn backend.api.app:app --host 127.0.0.1 --port 8001
```

**启动前端：**
```bat
cd src\frontend
npm run dev
```

---

## 数据

- **视频文件**：放在 `videos/` 目录下。
- **处理结果**：所有的转写、总结、笔记都存储在 `workspace/` 目录下。
- **本地模型**：自动下载的模型文件存储在 `data/models/` 目录下。
- **隐私说明**：除了向 LLM 提供商发送文本进行总结/对话外，所有音频处理和原始数据均保留在本地。

---

## 常见问题

**Q: 第一次运行生成概况很慢？**
A: 首次运行需要下载约 1.5GB 的转写模型，取决于网速。下载完成后，后续转写速度将大幅提升。

**Q: 前端页面显示“连接后端失败”？**
A: 请检查后端终端窗口是否有红色报错。通常是因为端口 8001 被占用或 `.env` 里的 API Key 格式不正确。

**Q: 如何更换转写语言？**
A: 修改 `config/settings.toml` 中的 `language = "zh"` 为你需要的语言代码。
