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
python tools/run_backend_tests.py --mysql-home $env:VSUMMARY_MYSQL_HOME tests/backend -q
cd src/frontend
npm test
```

先将 `VSUMMARY_MYSQL_HOME` 设置为实际的 MySQL runtime 目录（包含 `bin/mysqld`）。上面的启动器复用受管
MySQL 链路，在临时目录创建数据库、执行迁移，再运行 pytest；结束后关闭实例并清理目录。
Quality CI 使用同一入口，迁移、隔离、事务回滚和并发防重测试都会执行。

只运行不依赖数据库的测试时，可以设置 `PYTHONPATH=src;.` 后直接调用 pytest。
数据库测试在缺少 `VSUMMARY_TEST_MYSQL_URL` 时会明确跳过；该变量只能指向可丢弃的测试库。

测试返回数据优先构造生产 DTO、`SubmittedJob`、`JobSnapshot` 和 `JobEventSnapshot`。
外部服务需要模拟时，使用带接口约束的 `create_autospec(..., spec_set=True)`。
持久化测试应重新读取数据库验证状态和副作用，不能让 Mock 固定返回预期结果。

HTTP 测试通过 `_api_fixtures.py` 构造真实 `ApiContainer` 和 `WorkspaceServices`，
宿主依赖与工作区服务分开配置。夹具显式列出生产构造参数，新增必填字段时会报错；
调整不可变容器使用 `dataclasses.replace`，调整工作区服务使用 `replace_test_services`。
