"""Public Core API application factory.

The Local product composes its additional routes in ``backend.local.http.app``.
"""

from backend.api.common.app import create_app

__all__ = ["create_app"]
