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

源码版需要一个 MySQL 8.4 runtime，但不需要把它注册成 Windows 服务。`start.bat` 会优先使用 `VSUMMARY_MYSQL_HOME`，其次从系统 `PATH` 和 `%ProgramFiles%\MySQL` 自动发现；找到后由 VSummary 在 `127.0.0.1` 启动并管理私有实例。自动发现失败时，在终端执行以下命令，并重新打开终端：

```bat
setx VSUMMARY_MYSQL_HOME "D:\tools\mysql-8.4.9-winx64"
```

变量值是 MySQL 安装根目录，必须包含 `bin\mysqld.exe` 与 `share\`。数据目录和 DPAPI 加密的应用凭据保存在 `%LOCALAPPDATA%\VSummary\mysql`。

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

支持从源码运行：本地 Python 服务提供网页界面，ASR 使用 whisper.cpp / Metal，
检索模型使用 CPU。无需 NVIDIA CUDA，也不需要 MLX。尚未提供 `.app` / DMG 整合包；
Intel Mac 未验证。

### 安装

先安装 [Homebrew](https://brew.sh)，然后安装本机工具：

```bash
brew install mysql@8.4 whisper-cpp ffmpeg node@22
```

保留项目现有 Conda 环境的安装方式（Python 3.11）：

```bash
git clone https://github.com/alpha03123/vsummary.git
cd vsummary
conda env create -f environment.cpu.yml
conda activate vsummary
```

没有 Conda 时，也可用项目独立的 `.venv`，依赖仍使用同一份 `requirements.cpu.txt`：

```bash
brew install python@3.11
"$(brew --prefix python@3.11)/bin/python3.11" -m venv .venv
.venv/bin/python -m pip install -r requirements.cpu.txt
```

构建前端（Node.js 22.12 或更新版本；已有符合要求的 Node.js 也可使用）：

```bash
export PATH="$(brew --prefix node@22)/bin:$PATH"
cd src/frontend
npm ci
npm run build
cd ../..
./start.command
```

`start.command` 优先使用项目 `.venv`，否则查找名为 `vsummary` 的 Conda 环境。
它启动 VSummary 专用的 MySQL、执行数据库迁移，然后在服务就绪后打开
`http://127.0.0.1:4173`。前端由同一个服务提供，不需要另开 Vite。
退出时在启动终端按 `Ctrl+C`，数据库也会正常停止。不要为本应用运行
`brew services start mysql@8.4`；应用管理自己的实例，不使用 Homebrew 的共享数据库。

MySQL 默认从 `brew --prefix mysql@8.4` 查找。可用环境变量调整启动：

```bash
VSUMMARY_MYSQL_HOME=/path/to/mysql VSUMMARY_PORT=4174 ./start.command
# 为开发/测试隔离用户数据：
VSUMMARY_DATA="$PWD/data/mac-test" ./start.command
```

### 模型与首次配置

首次创建 `config/settings.toml` 时，Mac 默认选择 `whisper_cpp` 和 CPU embedding；
已有配置不会被覆盖。若之前使用过 Windows 配置，请在设置页改为：

```toml
[asr]
provider = "whisper_cpp"

[asr.whisper_cpp]
binary_path = "whisper-cli"
model = "large-v3-turbo-q5_0"

[agent_retrieval]
embedding_device = "cpu"
```

1. 在设置页下载 whisper.cpp 的 `large-v3-turbo-q5_0` 模型（约 547 MiB）。
   Homebrew 安装的 `whisper-cli` 使用 Metal；也可填写自行编译的可执行文件路径。
2. 在「模型供应商」中配置可用的 LLM API，供总结、知识卡和问答使用。
3. 在设置页下载 RAG 向量模型后再使用知识库问答。它需要 FastEmbed 的 ONNX 权重；
   普通 safetensors 或 MLX 模型不能直接替代。
4. 导入一段媒体，运行转写/总结，再打开视频查看结果或导出。

### 数据与凭据

- 从源码启动时，数据库、导入媒体和处理缓存默认位于项目的 `.vsummary/`；
  设置 `VSUMMARY_DATA` 可指定其他绝对路径。直接调用后端且未设置该变量时，
  macOS 默认使用 `~/Library/Application Support/VSummary/`。
- 本地 MySQL 密码保存在当前用户的 macOS 登录钥匙串，服务名为 `VSummary MySQL`；
  数据目录中的 `.keychain` 文件只是引用，不含密码。首次访问如有系统提示，请允许
  本次安装的 Python 访问该条目；钥匙串锁定时需先解锁。
- LLM API 配置仍保存在源码目录的 `.env`；模型位于 `data/models/`。
- 更换数据目录会创建独立数据库及钥匙串条目；不要只移动数据库而遗漏对应凭据。

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
