"""依赖注入容器与 FastAPI 依赖项。

把 ``ApiContainer`` 挂载到 ``request.app.state`` 上，并通过 FastAPI 的
``Depends`` 机制提供给各 API 路由使用。
"""

from __future__ import annotations

from typing import Annotated, cast
from pathlib import Path

from fastapi import Depends, Request

from backend.api.bootstrap import ApiContainer, build_api_container

ROOT = Path(__file__).resolve().parents[3]


def build_default_container() -> ApiContainer:
    """使用项目根目录构建默认的依赖注入容器。

    Returns:
        初始化完成的 ``ApiContainer`` 实例，包含所有注册的用例和端口实现。
    """
    return build_api_container(ROOT)


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
