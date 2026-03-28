# vsummary

一个面向 BYOK 场景的开源智能总结工具，聚焦音视频内容的本地转写、结构化总结与后续多模态扩展。

## 方向

- 本地优先，用户自带模型或 API Key
- 先做稳定的音频转写与分段总结
- 再逐步加入关键帧、OCR 与时间轴融合

## 当前状态

- 仓库当前只完成了项目初始化与目录规划
- `whisper.cpp` 已在本地做过可用性验证，但还没有纳入仓库
- 初期计划采用外部运行时与按需下载模型，不直接把模型文件提交到仓库
- 本地模型目录固定为 `data/models/`
- 产品愿景与阶段路线见 [docs/product-roadmap.md](E:/gittools/self/video_include/docs/product-roadmap.md)

## 初期目录

```text
vsummary/
├─ data/
│  └─ models/     本地模型目录，仅本机使用，不提交到 Git
├─ docs/          项目文档、设计草图、调研记录
├─ scripts/       构建、开发、模型准备等脚本
├─ src/
│  ├─ app/        用例编排与任务流程
│  ├─ domain/     核心领域模型与规则
│  ├─ infra/      外部依赖接入，如 ffmpeg、whisper.cpp、LLM
│  └─ presentation/ 对外入口，如 CLI、HTTP、桌面端适配
├─ tests/         测试代码
└─ third_party/   第三方源码或子模块，如 whisper.cpp
```

### 目录职责

- `src/domain` 只放业务概念，不依赖具体框架和厂商 SDK
- `src/app` 负责把转写、切分、总结这些流程串起来
- `src/infra` 负责与外部系统打交道，不把细节泄漏到核心逻辑
- `src/presentation` 作为入口层，后续可以按实际选择 CLI、桌面端或 Web API
- `third_party` 专门放外部项目，避免把三方代码和自有代码混在一起

## 依赖说明

`whisper.cpp` 目前不是仓库内置依赖。后续会在下面两种接入方式中二选一：

1. 将 `whisper.cpp` 源码或预编译运行时放入 [third_party](E:/gittools/self/video_include/third_party)
2. 由应用在初始化阶段下载 `whisper.cpp` 运行时与模型

在方案确定前，仓库不会提交 `whisper.cpp` 模型文件。这是为了避免仓库体积膨胀，也避免把第三方二进制和项目源码混在一起。

### 模型路径

- 本地模型统一放在 `data/models/`
- 该目录默认加入 `.gitignore`
- 当前测试使用的模型文件名是 `ggml-tiny.en.bin`

## 配置约定

- [config/settings.yaml](E:/gittools/self/video_include/config/settings.yaml) 用于保存公开配置
- `.env` 用于保存本地密钥，不提交到 Git
- [.env.example](E:/gittools/self/video_include/.env.example) 只提供环境变量模板

推荐分工：

- `settings.yaml`：设备选择、运行时路径、模型路径、公开接口地址、模型名
- `.env`：`OPENAI_API_KEY` 等敏感凭证

## 前端原型

- 前端原型位于 [frontend](E:/gittools/self/video_include/frontend)
- 当前使用 `Vite + React`，先直接读取 `summary.json` 和 `mindmap.json`
- 首次进入前端目录后安装依赖：

```powershell
cd frontend
npm install
```

- 本地开发：

```powershell
npm run dev
```

- 也可以在仓库根目录一键同时启动前后端：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\dev.ps1
```

- 更省事的方式是直接运行：

```powershell
.\dev.cmd
```

- 如果你当前就在 `scripts/` 目录里，运行：

```powershell
.\dev.cmd
```

- 生产构建：

```powershell
npm run build
```

- 开发服务器默认地址：
  - `http://127.0.0.1:4173`
- 后端开发接口默认地址：
  - `http://127.0.0.1:8000`
- 当前后端提供了一个很薄的 sample API：
  - `GET /api/health`
  - `GET /api/videos`
  - `GET /api/videos/{video_id}/summary`
- 你可以在页面内手动载入产物文件，也可以通过 URL 参数预载入：

```text
http://127.0.0.1:4173/?summary=/sample/output/<video>/summary.json&mindmap=/sample/output/<video>/mindmap.json
```
