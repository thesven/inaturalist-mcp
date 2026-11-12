"""iNaturalist Model Context Protocol (MCP) server."""

__version__ = "0.2.0"

from .client import (
    INaturalistAPIError,
    INaturalistClient,
    INaturalistError,
    INaturalistNotFoundError,
    INaturalistRateLimitError,
)
from .server import create_server, main, mcp

__all__ = [
    "INaturalistAPIError",
    "INaturalistClient",
    "INaturalistError",
    "INaturalistNotFoundError",
    "INaturalistRateLimitError",
    "__version__",
    "create_server",
    "main",
    "mcp",
]
