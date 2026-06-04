# Test Layout

后端测试按测试层级优先分类，功能域作为下一层目录：

- `backend/unit/`：纯逻辑、单模块或轻量依赖测试。
- `backend/integration/`：跨模块协作、FastAPI `TestClient`、真实网关封装或文件系统流程测试。
- `backend/architecture/`：架构边界和依赖方向约束测试。
- `fixtures/`：后端测试共享夹具数据。

前端测试集中在 `frontend/`，按源码功能域镜像分组：

- `frontend/features/**/model/*.test.*`：状态、数据转换、API 封装等模型层测试。
- `frontend/features/**/ui/*.test.*`：组件和视图模型测试。
- `frontend/features/**/ui/shared/*.test.*`：共享 UI 组件测试。

常用命令：

```powershell
python -m pytest tests/backend
cd src/frontend
npm test
```
