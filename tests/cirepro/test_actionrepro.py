from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from agentci.cirepro.analyze import analyze_paths
from agentci.cirepro.cli import main
from agentci.cirepro.report import to_json, to_markdown, to_pr_comment

FIXTURES = Path(__file__).parent / "fixtures"


def test_classifies_pytest_failure() -> None:
    analysis = analyze_paths([FIXTURES / "pytest_failure.log"])

    assert analysis.failures
    assert analysis.failures[0].category == "test_failure"
    assert analysis.failures[0].commands == ["python -m pytest -q"]
    assert "AssertionError" in "\n".join(analysis.failures[0].evidence)


def test_classifies_permission_gate_before_generic_error() -> None:
    analysis = analyze_paths([FIXTURES / "permission_gate.log"])

    assert analysis.failures[0].category == "permission_gate"
    assert "permission" in analysis.failures[0].advice.lower()


def test_classifies_network_429() -> None:
    analysis = analyze_paths([FIXTURES / "network_429.log"])

    categories = [failure.category for failure in analysis.failures]
    assert "network_external_service" in categories


def test_classifies_runner_memory_failure(tmp_path: Path) -> None:
    log = tmp_path / "oom.log"
    log.write_text(
        "test\tRun tests\t2026-06-14T00:00:00Z\t##[group]Run npm test\n"
        "test\tRun tests\t2026-06-14T00:00:01Z\tnpm test\n"
        "test\tRun tests\t2026-06-14T00:00:02Z\t"
        "FATAL ERROR: Reached heap limit Allocation failed - JavaScript heap out of memory\n"
        "test\tRun tests\t2026-06-14T00:00:03Z\t##[error]Process completed with exit code 137.\n",
        encoding="utf-8",
    )

    analysis = analyze_paths([log])

    assert analysis.failures[0].category == "runner_memory"
    assert "memory" in analysis.failures[0].advice.lower()


def test_reports_markdown_and_json() -> None:
    analysis = analyze_paths([FIXTURES / "pytest_failure.log"])

    markdown = to_markdown(analysis)
    payload = json.loads(to_json(analysis))

    assert "ActionRepro report" in markdown
    assert payload["failures"][0]["category"] == "test_failure"


def test_pr_comment_dry_run_text() -> None:
    analysis = analyze_paths([FIXTURES / "permission_gate.log"])

    comment = to_pr_comment(analysis)

    assert "permission_gate" in comment
    assert "maintainer" in comment.lower() or "external" in comment.lower()


def test_cli_plan_writes_markdown(tmp_path: Path) -> None:
    runner = CliRunner()
    out = tmp_path / "report.md"

    result = runner.invoke(
        main,
        ["plan", str(FIXTURES / "pytest_failure.log"), "--out", str(out)],
    )

    assert result.exit_code == 0, result.output
    assert "ActionRepro report" in out.read_text(encoding="utf-8")


def test_cli_plan_writes_pr_comment(tmp_path: Path) -> None:
    runner = CliRunner()
    out = tmp_path / "comment.md"

    result = runner.invoke(
        main,
        ["plan", str(FIXTURES / "permission_gate.log"), "--format", "comment", "--out", str(out)],
    )

    assert result.exit_code == 0, result.output
    text = out.read_text(encoding="utf-8")
    assert "first actionable signal" in text
    assert "permission_gate" in text


def test_cli_inspect() -> None:
    runner = CliRunner()

    result = runner.invoke(main, ["inspect", str(FIXTURES / "network_429.log")])

    assert result.exit_code == 0, result.output
    assert "ActionRepro findings" in result.output


def test_extract_command_keeps_runner_prefix() -> None:
    from agentci.cirepro.classifier import extract_command
    from agentci.cirepro.models import LogLine

    def _line(text: str) -> LogLine:
        return LogLine(
            source=Path("x.log"), number=1, job="test", step="Tests", timestamp="", text=text
        )

    # a runner prefix like `uv run` must be kept, not truncated to bare pytest
    assert (
        extract_command(_line("uv run pytest tests/test_embeddings.py"))
        == "uv run pytest tests/test_embeddings.py"
    )
    # the more specific `python -m pytest` form is still preserved in full
    assert extract_command(_line("python -m pytest tests/")) == "python -m pytest tests/"


def test_classifies_cache_corruption(tmp_path: Path) -> None:
    log = tmp_path / "cache.log"
    log.write_text(
        "test\tCache\t2026-06-14T00:00:00Z\t##[group]Restore node_modules cache\n"
        "test\tCache\t2026-06-14T00:00:01Z\tFailed to restore cache entry. "
        "tar: this does not look like a tar archive\n"
        "test\tCache\t2026-06-14T00:00:02Z\t##[error]Process completed with exit code 1.\n",
        encoding="utf-8",
    )

    analysis = analyze_paths([log])

    assert analysis.failures[0].category == "cache_corruption"
    assert "cache" in analysis.failures[0].advice.lower()
    assert "external/CI-gated" in to_pr_comment(analysis)


def test_classifies_flaky_retry(tmp_path: Path) -> None:
    log = tmp_path / "flaky.log"
    log.write_text(
        "test\tRun tests\t2026-06-14T00:00:00Z\t##[group]Run pytest\n"
        "test\tRun tests\t2026-06-14T00:00:01Z\t2 failed, 41 passed, 1 flaky in 31.2s\n"
        "test\tRun tests\t2026-06-14T00:00:02Z\t##[error]Process completed with exit code 1.\n",
        encoding="utf-8",
    )

    analysis = analyze_paths([log])

    assert analysis.failures[0].category == "flaky_retry"
    assert "external/CI-gated" in to_pr_comment(analysis)


def _two_run_logs(tmp_path: Path) -> tuple[Path, Path]:
    before = tmp_path / "before.log"
    after = tmp_path / "after.log"
    before.write_text(
        "ci\tRun tests\t2026-08-04T00:00:00Z\t##[group]Run npm test\n"
        "ci\tRun tests\t2026-08-04T00:00:00Z\tnpm test\n"
        "ci\tRun tests\t2026-08-04T00:00:00Z\t"
        "FAIL test_auth.py::test_login - AssertionError: boom after 45s\n"
        "ci\tRun tests\t2026-08-04T00:00:00Z\t##[error]Process completed with exit code 1.\n"
        "ci\tLint\t2026-08-04T00:00:00Z\t##[group]Run ruff check\n"
        "ci\tLint\t2026-08-04T00:00:00Z\truff check\n"
        "ci\tLint\t2026-08-04T00:00:00Z\tsrc/old.py:1:1: E501 line too long\n"
        "ci\tLint\t2026-08-04T00:00:00Z\t##[error]Process completed with exit code 1.\n",
        encoding="utf-8",
    )
    after.write_text(
        "ci\tRun tests\t2026-08-04T00:00:00Z\t##[group]Run npm test\n"
        "ci\tRun tests\t2026-08-04T00:00:00Z\tnpm test\n"
        "ci\tRun tests\t2026-08-04T00:00:00Z\t"
        "FAIL test_auth.py::test_login - AssertionError: boom after 51s\n"
        "ci\tRun tests\t2026-08-04T00:00:00Z\t##[error]Process completed with exit code 1.\n"
        "ci\tRun integration\t2026-08-04T00:00:00Z\t##[group]Run npm run integration\n"
        "ci\tRun integration\t2026-08-04T00:00:00Z\tnpm run integration\n"
        "ci\tRun integration\t2026-08-04T00:00:00Z\t"
        "FAIL test_pay.py::test_charge - KeyError: 'price'\n"
        "ci\tRun integration\t2026-08-04T00:00:00Z\t##[error]Process completed with exit code 1.\n",
        encoding="utf-8",
    )
    return before, after


def test_compare_splits_new_fixed_and_preexisting(tmp_path: Path) -> None:
    from agentci.cirepro.compare import compare_analyses

    before, after = _two_run_logs(tmp_path)
    cmp_result = compare_analyses(analyze_paths([before]), analyze_paths([after]))

    new_headlines = [f.headline for f in cmp_result.new_failures]
    assert any("test_charge" in h for h in new_headlines)
    # the E501 lint failure is fixed in the after run; its headline is the
    # generic ##[error] line, so assert on where it came from instead
    assert any(
        f.category == "lint_or_typecheck" and f.step == "Lint" for f in cmp_result.fixed_failures
    )
    # the login failure is the same failure with a different duration: still failing, not new
    assert any("test_login" in f.headline for f in cmp_result.still_failing)


def test_compare_cli_markdown(tmp_path: Path) -> None:
    before, after = _two_run_logs(tmp_path)
    result = CliRunner().invoke(main, ["compare", str(before), str(after)])

    assert result.exit_code == 0, result.output
    assert "## New failures" in result.output
    assert "## Fixed" in result.output
    assert "test_charge" in result.output
