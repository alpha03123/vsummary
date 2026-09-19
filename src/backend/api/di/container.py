"""依赖注入容器与 FastAPI 依赖项。

把 ``ApiContainer`` 挂载到 ``request.app.state`` 上，并通过 FastAPI 的
``Depends`` 机制提供给各 API 路由使用。
"""

from __future__ import annotations

from typing import Annotated, cast

from fastapi import Depends, Request

from backend.api.di.bootstrap import ApiContainer


def build_default_container() -> ApiContainer:
    """拒绝隐式文件工作区装配。

    生产启动必须先完成受管 MySQL 启动和旧工作区迁移，再显式注入 SQL
    Workspace。这样不会在一个遗漏的入口里重新启用旧 JSON 读写链路。
    """
    raise RuntimeError("VSummary requires an explicit SQL workspace container; start through backend.api.http.server.")


def get_container(request: Request) -> ApiContainer:
    """从请求的 ``app.state`` 中提取依赖注入容器。

    这是一个 FastAPI 依赖工厂函数，供 ``Depends(get_container)`` 使用。

    Args:
        request: 当前 HTTP 请求对象。

    Returns:
        挂载在应用状态上的 ``ApiContainer`` 实例。
    """
    return cast(ApiContainer, request.app.state.container)


# FastAPI 依赖注入标记：在路由签名中使用此类型即可自动获取 ``ApiContainer``。
ApiContainerDep = Annotated[ApiContainer, Depends(get_container)]
