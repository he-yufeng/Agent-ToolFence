from __future__ import annotations

import asyncio
import inspect
import json
import os
import shlex
import tempfile
import time
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass, field
from typing import Any, TextIO
from urllib.parse import urlsplit, urlunsplit

import httpx
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from .secrets import scan_text

try:
    from mcp.client.streamable_http import streamable_http_client as _http_transport
except ImportError:  # older mcp only has the old spelling
    from mcp.client.streamable_http import streamablehttp_client as _http_transport

# renamed in newer mcp: caller owns the httpx client instead of passing headers
_TRANSPORT_TAKES_HTTP_CLIENT = "http_client" in inspect.signature(_http_transport).parameters


@dataclass(frozen=True)
class Finding:
    code: str
    severity: str
    message: str
    target: str | None = None

    def to_dict(self) -> dict[str, str | None]:
        return {
            "code": self.code,
            "severity": self.severity,
            "message": self.message,
            "target": self.target,
        }


@dataclass(frozen=True)
class ToolSummary:
    name: str
    description: str | None
    has_input_schema: bool

    def to_dict(self) -> dict[str, str | bool | None]:
        return {
            "name": self.name,
            "description": self.description,
            "has_input_schema": self.has_input_schema,
        }


@dataclass
class CheckResult:
    command: str
    status: str
    duration_ms: int
    tools: list[ToolSummary] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)
    stderr_tail: str = ""

    @property
    def failed(self) -> bool:
        return any(f.severity == "error" for f in self.findings)

    @property
    def warned(self) -> bool:
        return any(f.severity == "warning" for f in self.findings)

    def to_dict(self) -> dict[str, Any]:
        return {
            "command": self.command,
            "status": self.status,
            "duration_ms": self.duration_ms,
            "tool_count": len(self.tools),
            "tools": [tool.to_dict() for tool in self.tools],
            "findings": [finding.to_dict() for finding in self.findings],
            "stderr_tail": self.stderr_tail,
        }


async def check_stdio_server(command_line: str, timeout: float = 20.0) -> CheckResult:
    started = time.monotonic()
    with tempfile.TemporaryFile(mode="w+", encoding="utf-8", errors="replace") as errlog:
        try:
            result = await asyncio.wait_for(
                _check_stdio_server(command_line, errlog),
                timeout=timeout,
            )
        except TimeoutError:
            result = CheckResult(
                command=command_line,
                status="failed",
                duration_ms=_elapsed_ms(started),
                findings=[
                    Finding(
                        code="server_timeout",
                        severity="error",
                        message=f"MCP server did not complete the handshake within {timeout:g}s.",
                    )
                ],
                stderr_tail=_tail(_read_errlog(errlog)),
            )
        except Exception as exc:
            if _elapsed_ms(started) >= int(timeout * 1000):
                result = _timeout_result(command_line, timeout, started, errlog)
            else:
                result = CheckResult(
                    command=command_line,
                    status="failed",
                    duration_ms=_elapsed_ms(started),
                    findings=[
                        Finding(
                            code="server_error",
                            severity="error",
                            message=f"MCP server check failed: {exc}",
                        )
                    ],
                    stderr_tail=_tail(_read_errlog(errlog)),
                )

    result.duration_ms = _elapsed_ms(started)
    return result


async def _check_stdio_server(command_line: str, errlog: TextIO) -> CheckResult:
    params = _server_params(command_line)

    async with stdio_client(params, errlog=errlog) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            tools_result = await session.list_tools()

    stderr_text = _read_errlog(errlog)
    tools = [_summarize_tool(tool) for tool in getattr(tools_result, "tools", [])]

    findings = _evaluate_tools(tools)
    findings.extend(_scan_observed_data(tools, stderr_text))

    return CheckResult(
        command=command_line,
        status=_status_for(findings),
        duration_ms=0,
        tools=tools,
        findings=findings,
        stderr_tail=_tail(stderr_text),
    )


async def check_http_server(
    url: str,
    headers: dict[str, str] | None = None,
    timeout: float = 20.0,
) -> CheckResult:
    started = time.monotonic()
    display_url = _display_url(url)
    try:
        result = await asyncio.wait_for(
            _check_http_server(url, headers, display_url),
            timeout=timeout,
        )
    except TimeoutError:
        result = _timeout_result(display_url, timeout, started, None)
    except Exception as exc:
        if _elapsed_ms(started) >= int(timeout * 1000):
            result = _timeout_result(display_url, timeout, started, None)
        else:
            result = CheckResult(
                command=display_url,
                status="failed",
                duration_ms=_elapsed_ms(started),
                findings=[
                    Finding(
                        code="server_error",
                        severity="error",
                        message=f"MCP server check failed: {exc}",
                    )
                ],
            )

    result.duration_ms = _elapsed_ms(started)
    return result


async def _check_http_server(
    url: str,
    headers: dict[str, str] | None,
    display_url: str,
) -> CheckResult:
    if _TRANSPORT_TAKES_HTTP_CLIENT:
        # no per-request timeout here, the outer wait_for is the only clock
        async with httpx.AsyncClient(
            headers=headers or {},
            follow_redirects=True,
            timeout=httpx.Timeout(None),
        ) as http_client:
            tools_result = await _list_tools(_http_transport(url, http_client=http_client))
    else:
        tools_result = await _list_tools(_http_transport(url, headers=headers or {}))

    tools = [_summarize_tool(tool) for tool in getattr(tools_result, "tools", [])]

    findings = _evaluate_tools(tools)
    findings.extend(_scan_observed_data(tools, ""))

    return CheckResult(
        command=display_url,
        status=_status_for(findings),
        duration_ms=0,
        tools=tools,
        findings=findings,
    )


async def _list_tools(transport_cm: AbstractAsyncContextManager[Any]) -> Any:
    async with transport_cm as (read_stream, write_stream, _):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            return await session.list_tools()


def _evaluate_tools(tools: list[ToolSummary]) -> list[Finding]:
    findings: list[Finding] = []
    if not tools:
        findings.append(
            Finding(
                code="no_tools",
                severity="warning",
                message="Server initialized, but tools/list returned no tools.",
            )
        )

    for tool in tools:
        if not tool.name.strip():
            findings.append(
                Finding(
                    code="tool_name_missing",
                    severity="error",
                    message="A tool has an empty name.",
                )
            )
        if not tool.has_input_schema:
            findings.append(
                Finding(
                    code="tool_schema_missing",
                    severity="error",
                    message="A tool is missing inputSchema.",
                    target=tool.name,
                )
            )
    return findings


def _status_for(findings: list[Finding]) -> str:
    if any(f.severity == "error" for f in findings):
        return "failed"
    if any(f.severity == "warning" for f in findings):
        return "warning"
    return "passed"


def _display_url(url: str) -> str:
    # tokens ride in query strings, keep them out of reports
    parts = urlsplit(url)
    if not parts.query and not parts.fragment:
        return url
    return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))


def _server_params(command_line: str) -> StdioServerParameters:
    parts = shlex.split(command_line, posix=os.name != "nt")
    if not parts:
        raise ValueError("--command cannot be empty")

    command = _strip_quotes(parts[0])
    args = [_strip_quotes(part) for part in parts[1:]]
    return StdioServerParameters(command=command, args=args)


def _strip_quotes(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def _summarize_tool(tool: Any) -> ToolSummary:
    name = str(getattr(tool, "name", "") or "")
    description = getattr(tool, "description", None)
    input_schema = getattr(tool, "inputSchema", None)
    if input_schema is None:
        input_schema = getattr(tool, "input_schema", None)

    return ToolSummary(
        name=name,
        description=str(description) if description else None,
        has_input_schema=isinstance(input_schema, dict) and bool(input_schema),
    )


def _scan_observed_data(tools: list[ToolSummary], stderr_text: str) -> list[Finding]:
    findings: list[Finding] = []
    for secret in scan_text(stderr_text, "server stderr"):
        findings.append(
            Finding(
                code="secret_leak",
                severity="error",
                message=f"Possible {secret.kind} leaked in {secret.where}.",
            )
        )

    metadata = json.dumps([tool.to_dict() for tool in tools], ensure_ascii=False)
    for secret in scan_text(metadata, "tool metadata"):
        findings.append(
            Finding(
                code="secret_leak",
                severity="error",
                message=f"Possible {secret.kind} leaked in {secret.where}.",
            )
        )
    return findings


def _elapsed_ms(started: float) -> int:
    return int((time.monotonic() - started) * 1000)


def _timeout_result(
    command_line: str,
    timeout: float,
    started: float,
    errlog: TextIO | None,
) -> CheckResult:
    return CheckResult(
        command=command_line,
        status="failed",
        duration_ms=_elapsed_ms(started),
        findings=[
            Finding(
                code="server_timeout",
                severity="error",
                message=f"MCP server did not complete the handshake within {timeout:g}s.",
            )
        ],
        stderr_tail=_tail(_read_errlog(errlog)) if errlog is not None else "",
    )


def _tail(text: str, max_chars: int = 2000) -> str:
    text = text.strip()
    if len(text) <= max_chars:
        return text
    return text[-max_chars:]


def _read_errlog(errlog: TextIO) -> str:
    try:
        errlog.flush()
        errlog.seek(0)
        return errlog.read()
    except OSError:
        return ""
