"""Analyze CI logs and produce failure objects."""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from .classifier import classify, extract_command, is_failure_line
from .models import Analysis, Failure, LogLine
from .parser import load_lines


def _window(lines: list[LogLine], index: int, radius: int = 4) -> list[LogLine]:
    # Evidence must stay inside the failure's own job/step: the next step's
    # content (lint, docs) otherwise bleeds into the classification and the
    # same failure can be judged differently depending on what follows it.
    job, step = lines[index].job, lines[index].step
    same_step = [i for i, line in enumerate(lines) if line.job == job and line.step == step]
    position = same_step.index(index)
    start = same_step[max(position - radius, 0)]
    last = same_step[min(position + radius, len(same_step) - 1)]
    return lines[start : last + 1]


def _commands_by_step(lines: list[LogLine]) -> dict[tuple[str, str], list[str]]:
    commands: dict[tuple[str, str], list[str]] = defaultdict(list)
    seen: set[tuple[str, str, str]] = set()
    for line in lines:
        command = extract_command(line)
        if not command:
            continue
        key = (line.job, line.step)
        dedupe_key = (line.job, line.step, command)
        if dedupe_key not in seen:
            commands[key].append(command)
            seen.add(dedupe_key)
    return commands


def analyze_paths(paths: list[str | Path], max_failures: int = 8) -> Analysis:
    resolved = [Path(path) for path in paths]
    lines = load_lines(resolved)
    commands = _commands_by_step(lines)
    failures: list[Failure] = []
    seen: set[tuple[str, str, str, str]] = set()

    for index, line in enumerate(lines):
        if not is_failure_line(line):
            continue
        nearby = _window(lines, index)
        evidence = [entry.text for entry in nearby if entry.text.strip()]
        category, advice = classify("\n".join(evidence), step=line.step)
        headline = line.text.strip() or f"{category} in {line.step}"
        key = (category, line.job, line.step)
        if key in seen:
            continue
        failures.append(
            Failure(
                category=category,
                job=line.job,
                step=line.step,
                source=line.source,
                line=line.number,
                headline=headline,
                evidence=evidence[-5:],
                commands=commands.get((line.job, line.step), [])[:4],
                advice=advice,
            )
        )
        seen.add(key)
        if len(failures) >= max_failures:
            break

    return Analysis(
        paths=resolved,
        failures=failures,
        command_count=sum(len(value) for value in commands.values()),
        line_count=len(lines),
    )
