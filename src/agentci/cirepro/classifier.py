"""Failure classification rules."""

from __future__ import annotations

from .models import LogLine

FAILURE_MARKERS = (
    "##[error]",
    "process completed with exit code",
    "traceback (most recent call last)",
    "assertionerror",
    "failed",
    "npm err!",
    "error:",
    "e   ",
)

COMMAND_HINTS = (
    "python -m pytest",
    "pytest",
    "ruff check",
    "mypy",
    "pyright",
    "npm test",
    "npm run",
    "pnpm",
    "yarn",
    "uv run",
    "go test",
    "cargo test",
)


def is_failure_line(line: LogLine) -> bool:
    lower = line.text.lower()
    return any(marker in lower for marker in FAILURE_MARKERS)


def classify(text: str, step: str = "") -> tuple[str, str]:
    haystack = f"{step}\n{text}".lower()

    if any(token in haystack for token in ("resource not accessible", "bad credentials")):
        return "permission_gate", "Workflow token, CLA, or integration permissions blocked the run."
    if any(token in haystack for token in ("403", "forbidden", "vercel", "secret source: none")):
        return "permission_gate", "The failure looks permission-gated rather than code-gated."
    if any(token in haystack for token in ("429", "too many requests", "couldn't connect")):
        return (
            "network_external_service",
            "External service or network availability blocked the run.",
        )
    if any(token in haystack for token in ("connection reset", "econnreset", "temporary failure")):
        return (
            "network_external_service",
            "Network instability blocked a dependency or test service.",
        )
    if any(token in haystack for token in ("no space left on device", "enospc", "disk quota")):
        return "runner_disk", "The runner ran out of disk space."
    if any(
        token in haystack
        for token in (
            "out of memory",
            "oom-killed",
            "oom killed",
            "exit code 137",
            "heap out of memory",
            "killed process",
        )
    ):
        return "runner_memory", "The runner likely ran out of memory."
    if any(token in haystack for token in ("timed out", "timeout", "cancelled after")):
        return "flaky_timeout", "The failing step timed out or behaved like a flaky run."
    if any(
        token in haystack
        for token in (
            "failed to restore cache",
            "not look like a tar archive",
            "checksum mismatch",
            "cache corrupted",
            "unable to reserve cache",
        )
    ):
        return (
            "cache_corruption",
            "The CI cache restore or reserve step failed; rerun or drop the cache.",
        )
    if any(
        token in haystack
        for token in ("flaky", "flakefinder", "passed on retry", "tests failed, then passed")
    ):
        return (
            "flaky_retry",
            "The failure looks flaky and may pass on rerun; rerun before digging.",
        )
    if any(token in haystack for token in ("pip install", "could not find a version", "npm err!")):
        return "dependency_install", "A dependency install or package resolution step failed."
    if any(
        token in haystack for token in ("ruff", "flake8", "pylint", "mypy", "pyright", "eslint")
    ):
        return "lint_or_typecheck", "A lint, formatting, or type-check command failed."
    if any(token in haystack for token in ("pytest", "test ", "tests/", "assertionerror", "e   ")):
        return "test_failure", "A test failed and should be reproduced locally."
    return "unknown_failure", "The failure is real, but the first-pass rules could not classify it."


def extract_command(line: LogLine) -> str | None:
    text = line.text.strip()
    if text.startswith("Run "):
        return text[4:].strip()
    if "]Run " in text:
        return text.split("]Run ", 1)[1].strip()

    lower = text.lower()
    # Return from the hint that appears earliest in the text, not first in the
    # tuple — otherwise a runner prefix like `uv run pytest` is truncated to
    # `pytest`, which won't reproduce the failure in the CI's managed env.
    best_pos = None
    for hint in COMMAND_HINTS:
        pos = lower.find(hint)
        if pos >= 0 and (best_pos is None or pos < best_pos):
            best_pos = pos
    if best_pos is not None:
        return text[best_pos:].strip()
    return None
