from __future__ import annotations

import runpy
import sys
from unittest.mock import MagicMock, patch

import pytest

from inaturalist_mcp import __version__
from inaturalist_mcp.server import main


def test_cli_version(capsys) -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(["--version"])
    assert exc_info.value.code == 0
    captured = capsys.readouterr()
    assert __version__ in captured.out


def test_cli_stdio_run() -> None:
    mock_run = MagicMock()
    with patch("inaturalist_mcp.server.mcp.run", mock_run):
        main(["--transport", "stdio"])
        mock_run.assert_called_once_with(transport="stdio")


def test_cli_sse_run() -> None:
    mock_run = MagicMock()
    with patch("inaturalist_mcp.server.mcp.run", mock_run):
        main(["--transport", "sse", "--port", "9000"])
        mock_run.assert_called_once_with(transport="sse")


def test_cli_invalid_transport() -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(["--transport", "invalid"])
    assert exc_info.value.code != 0


def test_module_main_run() -> None:
    mock_run = MagicMock()
    with patch("inaturalist_mcp.server.mcp.run", mock_run):
        with patch.object(sys, "argv", ["inaturalist-mcp", "--transport", "stdio"]):
            runpy.run_module("inaturalist_mcp.__main__", run_name="__main__")
        mock_run.assert_called_once_with(transport="stdio")
