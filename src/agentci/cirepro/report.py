"""Markdown and JSON rendering."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from .models import Analysis, Failure


def failure_to_dict(failure: Failure) -> dict[str, object]:
    data = asdict(failure)
    data["source"] = str(failure.source)
    return data


def to_json(analysis: Analysis) -> str:
    payload = {
        "paths": [str(path) for path in analysis.paths],
        "line_count": analysis.line_count,
        "command_count": analysis.command_count,
        "failures": [failure_to_dict(failure) for failure in analysis.failures],
    }
    return json.dumps(payload, indent=2, ensure_ascii=False)


def _comment_for_failure(failure: Failure) -> str:
    command_lines = "\n".join(f"- `{command}`" for command in failure.commands) or "- Pending"
    evidence_lines = "\n".join(f"> {item}" for item in failure.evidence[-3:])
    return (
        f"### {failure.category}: {failure.step}\n\n"
        f"{failure.advice}\n\n"
        f"Likely local repro command(s):\n\n{command_lines}\n\n"
        f"Evidence:\n\n{evidence_lines}\n"
    )


def to_markdown(analysis: Analysis) -> str:
    lines = [
        "# ActionRepro report",
        "",
        f"- Log files: {len(analysis.paths)}",
        f"- Lines scanned: {analysis.line_count}",
        f"- Commands detected: {analysis.command_count}",
        f"- Failures detected: {len(analysis.failures)}",
        "",
    ]
    if not analysis.failures:
        lines.extend(
            [
                "No obvious failure marker was found.",
                "",
                (
                    "Check whether the log was truncated or whether the failed job stores output "
                    "elsewhere."
                ),
            ]
        )
        return "\n".join(lines) + "\n"

    for index, failure in enumerate(analysis.failures, start=1):
        lines.extend(
            [
                f"## {index}. {failure.category}",
                "",
                f"- Job: `{failure.job}`",
                f"- Step: `{failure.step}`",
                f"- Source: `{failure.source}:{failure.line}`",
                f"- Headline: `{failure.headline}`",
                f"- Advice: {failure.advice}",
                "",
                "### Local repro commands",
                "",
            ]
        )
        if failure.commands:
            lines.extend(f"- `{command}`" for command in failure.commands)
        else:
            lines.append("- No command was extracted from this step.")
        lines.extend(["", "### Evidence", ""])
        lines.extend(f"> {item}" for item in failure.evidence)
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def to_pr_comment(analysis: Analysis) -> str:
    if not analysis.failures:
        return "I scanned the CI log with ActionRepro and did not find a clear failure marker."
    first = analysis.failures[0]
    base = (
        "I checked the CI failure and the first actionable signal looks like this:\n\n"
        f"{_comment_for_failure(first)}\n"
    )
    if first.category in {
        "permission_gate",
        "network_external_service",
        "runner_disk",
        "flaky_retry",
        "cache_corruption",
    }:
        return base + (
            "I will treat this as external/CI-gated unless the rerun shows a code failure."
        )
    return base + "I will reproduce the command locally and update the PR with the result."


def write_report(analysis: Analysis, out: str | Path, fmt: str) -> Path:
    path = Path(out)
    if path.parent != Path("."):
        path.parent.mkdir(parents=True, exist_ok=True)
    if fmt == "json":
        path.write_text(to_json(analysis) + "\n", encoding="utf-8")
    else:
        path.write_text(to_markdown(analysis), encoding="utf-8")
    return path
