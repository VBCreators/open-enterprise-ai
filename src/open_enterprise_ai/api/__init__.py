"""Global API package and routing."""

from open_enterprise_ai.api.router import api_router
from open_enterprise_ai.api.v1 import v1_router

__all__ = ["api_router", "v1_router"]
