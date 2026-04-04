# vsummary

一个面向 BYOK 场景的开源智能总结工具，聚焦音视频内容的本地转写、结构化总结与后续多模态扩展。

## 方向

- 本地优先，用户自带模型或 API Key
- 先做稳定的音频转写与分段总结
- 再逐步加入关键帧、OCR 与时间轴融合

## 当前状态

- 仓库处于重构阶段，后端正在从按技术层组织调整为按功能组织
- 本地模型目录固定为 `data/models/`，整个 `data/` 目录不提交到 Git
- 输入视频放在 `videos/<series>/`，处理产物输出到 `workspace/<series>/<video>/`
- 当前默认且唯一的转写实现为 `faster-whisper`
- 产品愿景与阶段路线见 [docs/product-roadmap.md](E:/gittools/self/video_include/docs/product-roadmap.md)

## 目录结构

```text
vsummary/
├─ config/         公开配置
├─ data/           本地运行数据，不提交到 Git
├─ docs/           项目文档、设计草图、调研记录
├─ scripts/        构建、开发、样例执行脚本
├─ videos/         本地视频输入，按 series 分组，不提交到 Git
├─ workspace/      本地处理中间产物与总结结果，不提交到 Git
├─ src/
│  ├─ backend/
│  │  ├─ api/                  FastAPI 入口与组装
│  │  └─ video_summary/        视频总结主能力
│  │     ├─ domain/            领域模型
│  │     ├─ generation/        转写与总结生成流程
│  │     ├─ library/           series / videos 浏览与生成流程
│  │     └─ infrastructure/    外部依赖实现与文件系统适配
│  └─ frontend/                Vite + React 前端工程
├─ tests/          测试代码
└─ sample/         历史样例目录，已不作为主工作流
```

## 架构说明

- `src/backend/video_summary/domain` 只放视频总结领域模型
- `src/backend/video_summary/generation` 负责转写与总结生成
- `src/backend/video_summary/library` 负责 series 浏览、视频选择与生成入口
- `src/backend/video_summary/infrastructure` 实现 ffmpeg、faster-whisper、OpenAI 与文件系统适配
- `src/backend/api` 是后端对外入口与依赖组装层
- `src/frontend` 保持为独立前端工程，不和后端实现细节混放

## 模型与依赖

- 本地模型统一放在 `data/models/`
- 该目录不会进入版本控制
- `faster-whisper` 模型下载到 `data/models/faster-whisper/<model_id>/`

## 配置约定

- [config/settings.toml](E:/gittools/self/video_include/config/settings.toml) 用于保存公开配置和工作区设置
- `.env` 用于保存本地密钥，不提交到 Git
- [.env.example](E:/gittools/self/video_include/.env.example) 只提供环境变量模板

推荐分工：

- `settings.toml`：转写设备、模型质量、公开接口地址，以及前端工作区设置
- `.env`：`OPENAI_API_KEY` 等敏感凭证

## 前端开发

- 前端工程位于 [src/frontend](E:/gittools/self/video_include/src/frontend)
- 首次进入前端目录后安装依赖：

```powershell
cd src/frontend
npm install
```

- 本地开发：

```powershell
npm run dev
```

- 生产构建：

```powershell
npm run build
```

## 联调开发

- 一键同时启动前后端：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\dev.ps1
```

- 如果当前就在 `scripts/` 目录中：

```powershell
.\dev.cmd
```

- 前端开发服务器默认地址：
  - `http://127.0.0.1:4173`
- 后端开发接口默认地址：
  - `http://127.0.0.1:8001`

## 测试

- 运行后端快速测试组：

```powershell
python .\scripts\run_backend_tests.py
```

- 查看所有后端测试分组：

```powershell
python .\scripts\run_backend_tests.py --list
```

- 按职责运行指定测试组：

```powershell
python .\scripts\run_backend_tests.py agent
python .\scripts\run_backend_tests.py api
python .\scripts\run_backend_tests.py summary
python .\scripts\run_backend_tests.py workspace
python .\scripts\run_backend_tests.py all
```

```powershell
python .\scripts\run_backend_tests.py tests.test_api
python .\scripts\run_backend_tests.py agent workspace
python .\scripts\run_backend_tests.py tests\test_generate_summary.py
```

推荐约定：

- 日常改 Agent：跑 `agent`
- 改文件系统、状态跟踪：跑 `workspace`
- 改总结生成流程：跑 `summary`
- 改 FastAPI 接口或组装：跑 `api`
- 只改某一个测试文件：直接传 `tests.test_xxx` 或 `tests\test_xxx.py`
- 一次涉及多个职责：把多个目标并列传进去
- 提交前做一次完整检查：跑 `all`

## 当前 API

- `GET /api/health`
- `GET /api/videos`
- `GET /api/videos/{series_id}/{video_id}/summary`
- `POST /api/videos/{series_id}/{video_id}/generate`

## 使用方式

- 把视频放进 `videos/<series>/`
- 前端会把 `videos` 下的一级目录识别为 series
- 选择某个视频后，如果还没有处理结果，可以点击 `Generate Video`
- 处理中间文件和最终结果会写到 `workspace/<series>/<video_stem>/`
