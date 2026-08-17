# 常见问题

## 1. `cublas.dll not found` / `cudart64_12.dll` / `cudnn` 报错

说明当前 GPU 运行时没有就绪。

建议顺序：

1. 确认你是通过 `environment.yml` 创建环境
2. 确认后端是从这个环境启动的
3. 如果还不行，先改回 CPU：

```toml
[asr.faster_whisper]
device = "cpu"
```

## 2. HuggingFace 下载很慢 / 失败

在 `.env` 中加入：

```dotenv
HF_ENDPOINT=https://hf-mirror.com
```

然后重启后端。

## 3. Windows 笔记本 GPU 版仍然走 CPU / 需要手动分配独显

在带有核显 + NVIDIA 独显的 Windows 笔记本上，系统可能把整合包里的 Python 后端进程分配到省电显卡，导致 GPU 版依赖已经安装，但运行时仍然只看到 CPU。

整合包后端实际运行的是：

```text
<解压目录>\runtime\python.exe
```

不是 `start.bat`，也不是浏览器。因此如果需要手动指定独显，请在 Windows 的 **设置 > 系统 > 显示 > 图形** 中添加这个 `runtime\python.exe`，并设置为 **高性能 / NVIDIA GPU**。

可以用下面命令确认 ONNX Runtime 当前可用的 provider：

```bat
cd /d <解压目录>
runtime\python.exe -c "import onnxruntime as ort; print(ort.__version__); print(ort.get_available_providers())"
```

如果输出只有：

```text
['CPUExecutionProvider']
```

说明 FastEmbed / ONNX Runtime 没有启用 CUDA。手动分配独显只解决 Windows 显卡调度问题；如果仍然没有 `CUDAExecutionProvider`，还需要继续检查 `onnxruntime-gpu` 是否被 CPU 版覆盖、CUDA / cuDNN DLL 是否完整、NVIDIA 驱动是否匹配，以及启动脚本是否把 `runtime` 下的 DLL 目录加入了 `PATH`。

## 4. 未找到 whisper.cpp 可执行文件：`whisper-cli`

该错误表示当前选择了“本地 whisper.cpp”转写引擎，但系统无法找到 `whisper-cli`。`whisper-cli` 是 whisper.cpp 提供的外部可执行文件，项目不会自动下载。

请按[安装文档](installation.md)下载或构建 whisper.cpp，然后选择以下任一方式配置：

1. 将 `whisper-cli.exe` 所在目录加入系统 `PATH`，并在命令行执行 `where.exe whisper-cli` 确认可以找到；
2. 在项目根目录的 `config/settings.toml` 中指定可执行文件的绝对路径：

```toml
[asr.whisper_cpp]
binary_path = "C:/path/to/whisper-cli.exe"
model = "large-v3-turbo-q5_0"
```

还需要在设置页下载与该引擎匹配的 GGML 模型。`whisper_cpp` 与 `faster_whisper` 的模型格式不能互用。保存配置后重启应用。

如果不准备使用 whisper.cpp，可以在设置中将转写引擎切换为 `faster_whisper` 或 `aliyun_bailian`。
