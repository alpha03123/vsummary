<div align="center">

<img src="./assets/logo.svg" width="128" alt="vsummary logo" />

# vsummary

视频AI总结，对话的本地知识库工具

![Python](https://img.shields.io/badge/Python-3.11-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-Backend-009688?logo=fastapi&logoColor=white)
![React](https://img.shields.io/badge/React-19-61DAFB?logo=react&logoColor=222)
![Vite](https://img.shields.io/badge/Vite-Frontend-646CFF?logo=vite&logoColor=white)
![LangGraph](https://img.shields.io/badge/LangGraph-Agent%20Workflow-1C3C3C)
![LlamaIndex](https://img.shields.io/badge/LlamaIndex-RAG-8A5CF6)
![faster--whisper](https://img.shields.io/badge/faster--whisper-Local%20ASR-2E8B57)
![LanceDB](https://img.shields.io/badge/LanceDB-Vector%20Search-FF6B00)
![License](https://img.shields.io/github/license/alpha03123/vsummary?label=License)

</div>


---

## 功能展示

### 系列对话

<img src="./assets/showcase-series-chat.png" alt="系列级对话页面" />

### 视频 AI 概况

在 AI 概况里，**点击章节卡片**或展开后的**转写段**即可直接跳到视频对应时间并自动播放。

<img src="assets/showcase-video-overview.gif" alt="视频 AI 概况页面" />

### 多弹性布局

可自由拆分、组合预览、逐字稿、AI 概括等面板；拖拽分割线即可调整比例，布局会自动保留。

<img src="./assets/showcase-flexible-layout.gif" alt="多弹性面板布局" />

### 聊天抽屉

点击工具栏的 💬 按钮从右侧滑出分析助手；按 `Esc` 或点击背景即可关闭。播放器继续播放，不被打断。

<img src="./assets/showcase-chat-drawer.png" alt="聊天抽屉" />

### 浏览器插件
支持直接解析B站视频，并且能够实现插件--视频位置的跳转
<img src="./assets/browser-plugin.png" alt="浏览器插件" />

### MCP：整理本地录音

将 VSummary 接入 MCP 后，AI 助手可以创建系列、导入本地媒体、发起处理并导出 Markdown。下面演示将两段录音处理为一份可编辑的结构化总结。

<img src="./assets/showcase-mcp-recording-summary.gif" alt="MCP 处理并总结本地录音" />

## 核心特性

- **把视频变成可检索的知识库**：导入本地视频后，自动整理出转写文本、概况、章节和关键结论。后续可以直接围绕内容提问，把视频作为自己的本地知识库。支持导出为MD。
- **按系列管理学习资料**：适合课程、讲座、播客、会议录像等成组视频。你可以在一个系列里批量处理视频，并从系列视角理解整体内容。
- **单个视频深度阅读**：每个视频都有独立工作区，可以查看原视频、AI 概况、章节摘要、思维导图、知识卡片和笔记，适合精读一段长视频。
- **章节与转写一键跳转**：在 AI 概况中，**点击章节卡**或展开后的**任意转写段**即可直接跳到视频对应时间并自动播放，导航视频内容更直观。
- **围绕视频内容对话**：可以在单视频或整个系列范围内提问，让系统基于已经整理好的转写、摘要、笔记和知识卡片回答。
- **外部课程导入**：支持 Bilibili,抖音,youtube 外链导入
- **MCP 自动化工作流**：通过 MCP 工具让 AI 助手创建和管理视频系列，导入本地媒体或 Bilibili 链接，跟踪处理进度，并导出 Markdown。
- **本地优先**：原始视频、转写结果、摘要、笔记和知识索引都保存在本地目录中；除了调用你配置的模型供应商外，不需要把视频上传到第三方平台。
- **低门槛启动**：提供 CPU / GPU 两种整合包，普通用户下载整合包解压后运行 `start.bat` 即可使用

---

## 快速开始

- [安装、硬件与 ASR 配置](docs/installation.md)：Windows NVIDIA、Windows AMD、macOS 的环境、模型与启动方式。

### 源码版 MySQL

Windows 整合包自带 MySQL，不需要安装 Windows 服务。源码版的 `start.bat` 会依次从 `VSUMMARY_MYSQL_HOME`、系统 `PATH`、`%ProgramFiles%\MySQL` 自动寻找 MySQL；找到后由应用在本机回环地址启动私有实例并管理迁移，不使用系统 MySQL 服务。

macOS / Apple Silicon 可按[安装说明](docs/installation.md#macos--apple-silicon)从源码运行，使用 whisper.cpp / Metal 转写；通过 `start.command` 启动本地网页和专用 MySQL。

## 浏览器插件

VSummary 提供 Chrome 浏览器插件。观看 Bilibili 视频时，可以直接在浏览器侧边栏中查看 AI 概况、章节、思维导图、知识卡片和笔记，并围绕当前视频提问。

Windows 整合包解压后，插件位于 `extensions/bilibili-sidepanel`。启动 VSummary 后，在 Chrome 的扩展程序页面选择“加载已解压的扩展程序”，然后选择这个文件夹即可。

- [浏览器插件安装与使用教程](docs/browser-extension.md)

## 数据目录

- `%LOCALAPPDATA%\VSummary\blobs/`：当前版本的视频和二进制制品；设置 `VSUMMARY_DATA` 时使用指定的数据根目录
- `videos/`、`workspace/`：旧版本的原始视频和工作产物；旧目录导入由“设置 → 应用更新 → 旧版数据迁移”启动
- `data/models/`：本地模型文件




## 常见问题

常见问题见 [docs/questions.md](docs/questions.md)。
## 沟通和联系
- QQ群:点击链接加入群聊【vsummary交流沟通群】：https://qm.qq.com/q/nxKBApDVF

<img src="./assets/qq-group-qrcode.jpg" width="240" alt="vsummary 交流群二维码" />
