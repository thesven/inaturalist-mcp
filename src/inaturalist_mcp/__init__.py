"""iNaturalist Model Context Protocol (MCP) server."""

__version__ = "1.0.0"

from .client import (
    INaturalistAPIError,
    INaturalistClient,
    INaturalistError,
    INaturalistNotFoundError,
    INaturalistRateLimitError,
    LeakyBucketLimiter,
    SimpleCache,
)
from .server import create_server, main, mcp

__all__ = [
    "INaturalistAPIError",
    "INaturalistClient",
    "INaturalistError",
    "INaturalistNotFoundError",
    "INaturalistRateLimitError",
    "LeakyBucketLimiter",
    "SimpleCache",
    "__version__",
    "create_server",
    "main",
    "mcp",
]
