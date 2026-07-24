from __future__ import annotations

import asyncio
import contextlib
import socket
import subprocess
import sys
import time
from collections.abc import Iterator
from pathlib import Path

from agentci.mcpgate.checker import check_http_server, check_stdio_server

FIXTURES = Path(__file__).parent / "fixtures"


def command_for(name: str) -> str:
    return f'"{sys.executable}" "{FIXTURES / name}"'


@contextlib.contextmanager
def http_fixture(name: str) -> Iterator[str]:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]

    proc = subprocess.Popen(
        [sys.executable, str(FIXTURES / name), str(port)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        _wait_for_port(port)
        yield f"http://127.0.0.1:{port}/mcp"
    finally:
        proc.terminate()
        proc.wait(timeout=5)


def _wait_for_port(port: int, timeout: float = 10.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                return
        except OSError:
            time.sleep(0.1)
    raise RuntimeError(f"fixture server on port {port} did not start")


def unused_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def test_good_server_passes() -> None:
    result = asyncio.run(check_stdio_server(command_for("good_server.py"), timeout=10))

    assert result.status == "passed"
    assert [tool.name for tool in result.tools] == ["echo"]
    assert result.findings == []


def test_empty_server_warns() -> None:
    result = asyncio.run(check_stdio_server(command_for("empty_server.py"), timeout=10))

    assert result.status == "warning"
    assert any(finding.code == "no_tools" for finding in result.findings)


def test_secret_in_tool_metadata_fails() -> None:
    result = asyncio.run(check_stdio_server(command_for("secret_server.py"), timeout=10))

    assert result.status == "failed"
    assert any(finding.code == "secret_leak" for finding in result.findings)


def test_crash_server_fails() -> None:
    result = asyncio.run(check_stdio_server(command_for("crash_server.py"), timeout=10))

    assert result.status == "failed"
    assert any(finding.code == "server_error" for finding in result.findings)


def test_timeout_server_fails() -> None:
    result = asyncio.run(check_stdio_server(command_for("timeout_server.py"), timeout=0.5))

    assert result.status == "failed"
    assert any(finding.code == "server_timeout" for finding in result.findings)


def test_http_good_server_passes() -> None:
    with http_fixture("good_http_server.py") as url:
        result = asyncio.run(check_http_server(url, timeout=10))

    assert result.status == "passed"
    assert [tool.name for tool in result.tools] == ["echo"]
    assert result.findings == []


def test_http_secret_in_tool_metadata_fails() -> None:
    with http_fixture("secret_http_server.py") as url:
        result = asyncio.run(check_http_server(url, timeout=10))

    assert result.status == "failed"
    assert any(finding.code == "secret_leak" for finding in result.findings)


def test_http_unreachable_server_fails() -> None:
    url = f"http://127.0.0.1:{unused_port()}/mcp"
    result = asyncio.run(check_http_server(url, timeout=5))

    assert result.status == "failed"
    assert any(finding.code == "server_error" for finding in result.findings)


def test_http_url_query_string_stays_out_of_result() -> None:
    url = f"http://127.0.0.1:{unused_port()}/mcp?api_key=sk-secret"
    result = asyncio.run(check_http_server(url, timeout=5))

    assert result.command == url.split("?")[0]
    assert "sk-secret" not in str(result.to_dict())
