from __future__ import annotations

import asyncio
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

from . import __version__
from .checker import CheckResult, check_http_server, check_stdio_server
from .report import write_json_report, write_markdown_report


@click.group(context_settings={"help_option_names": ["-h", "--help"]})
@click.version_option(__version__, prog_name="mcpready")
def cli() -> None:
    """CI gate for MCP servers."""


@cli.command()
@click.option(
    "--command",
    "command_line",
    help="Command that starts a stdio MCP server.",
)
@click.option("--url", help="Streamable HTTP URL of a remote MCP server.")
@click.option(
    "--header",
    "header_values",
    multiple=True,
    help="HTTP header as 'Name: value', repeatable. Only used with --url.",
)
@click.option("--timeout", type=float, default=20.0, show_default=True, help="Handshake timeout.")
@click.option("--report", type=click.Path(path_type=Path), help="Write a Markdown report.")
@click.option("--json", "json_path", type=click.Path(path_type=Path), help="Write a JSON report.")
@click.option("--fail-on-warn", is_flag=True, help="Return a non-zero exit code on warnings.")
def check(
    command_line: str | None,
    url: str | None,
    header_values: tuple[str, ...],
    timeout: float,
    report: Path | None,
    json_path: Path | None,
    fail_on_warn: bool,
) -> None:
    """Check an MCP server over stdio or streamable HTTP."""

    if bool(command_line) == bool(url):
        raise click.UsageError("pass exactly one of --command or --url")
    if header_values and not url:
        raise click.UsageError("--header only makes sense with --url")

    if command_line:
        result = asyncio.run(check_stdio_server(command_line, timeout=timeout))
    else:
        headers = _parse_headers(header_values)
        result = asyncio.run(check_http_server(url, headers=headers, timeout=timeout))

    if report:
        write_markdown_report(result, report)
    if json_path:
        write_json_report(result, json_path)

    _print_result(result)

    if result.failed or (fail_on_warn and result.warned):
        raise click.exceptions.Exit(1)


def _parse_headers(values: tuple[str, ...]) -> dict[str, str]:
    headers: dict[str, str] = {}
    for value in values:
        name, sep, header_value = value.partition(":")
        if not sep or not name.strip():
            raise click.UsageError(f"--header expects 'Name: value', got {value!r}")
        headers[name.strip()] = header_value.strip()
    return headers


def _print_result(result: CheckResult) -> None:
    console = Console()

    table = Table(title="MCPReady")
    table.add_column("Status")
    table.add_column("Tools", justify="right")
    table.add_column("Duration", justify="right")
    table.add_row(result.status, str(len(result.tools)), f"{result.duration_ms}ms")
    console.print(table)

    if result.findings:
        findings = Table(title="Findings")
        findings.add_column("Severity")
        findings.add_column("Code")
        findings.add_column("Target")
        findings.add_column("Message")
        for finding in result.findings:
            findings.add_row(
                finding.severity,
                finding.code,
                finding.target or "",
                finding.message,
            )
        console.print(findings)


if __name__ == "__main__":
    cli()
