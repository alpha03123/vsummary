# Backend Architecture Toolkit

这个目录存放两类内容：

- `*-current.mmd`：从代码实际 import 关系导出的现状图
- `*-target.mmd`：人工维护的目标架构图

## 开发依赖

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
```

## 导出现状图

导出后端顶层包关系：

```powershell
.\.venv\Scripts\python.exe scripts\analysis\export_backend_architecture.py `
  --module backend `
  --output docs\architecture\backend-current.mmd
```

导出 `video_summary` 子系统关系：

```powershell
.\.venv\Scripts\python.exe scripts\analysis\export_backend_architecture.py `
  --module backend.video_summary `
  --output docs\architecture\backend-video_summary-current.mmd
```

Mermaid 图里：

- 节点 `out` 表示该子包对外发出的直接模块依赖数量
- 节点 `in` 表示该子包被其他兄弟子包直接依赖的数量
- 边上的数字表示聚合后的直接模块 import 数量

## 执行架构规则检查

```powershell
.\.venv\Scripts\python.exe scripts\analysis\check_backend_architecture.py --show-timings
```

如果只想看某一条 contract：

```powershell
.\.venv\Scripts\python.exe scripts\analysis\check_backend_architecture.py `
  --contract backend_top_level_acyclic
```

## 规则设计原则

- 先用少量高价值规则卡住明显错误边界
- 让规则聚焦包级依赖，而不是一开始细到文件级
- 当前规则允许直接暴露现有架构问题，不用 `ignore_imports` 把问题藏起来
