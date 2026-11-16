"""Dependency-free product identity and runtime defaults."""

from importlib.metadata import version

PRODUCT_NAME = "Cache Me If You Can"
PRODUCT_ID = "cache-me-if-you-can"
MCP_SERVER_KEY = "cache_me"
DEFAULT_PORT = 52761


def product_version() -> str:
    """Read the installed distribution version without duplicating project metadata."""
    return version("cache-me")
