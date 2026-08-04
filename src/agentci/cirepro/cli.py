"""Command-line interface for ActionRepro."""

from __future__ import annotations

from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

from . import __version__
from .analyze import analyze_paths
from .github import fetch_run_log
from .report import to_json, to_markdown, to_pr_comment, write_report

console = Console()


@click.group()
@click.version_option(__version__, prog_name="actionrepro")
def main() -> None:
    """Turn CI logs into local repro plans."""


@main.command("fetch")
@click.argument("repo")
@click.argument("run_id")
@click.option("--out", type=click.Path(dir_okay=False), help="Output log file.")
def fetch_cmd(repo: str, run_id: str, out: str | None) -> None:
    """Fetch a GitHub Actions run log through gh."""
    output = out or f"actionrepro-{run_id}.log"
    path = fetch_run_log(repo, run_id, output)
    console.print(f"[green]Wrote log:[/green] {path}")


@main.command("inspect")
@click.argument("paths", nargs=-1, required=True, type=click.Path(exists=True, dir_okay=False))
def inspect_cmd(paths: tuple[str, ...]) -> None:
    """Show detected failures in a table."""
    analysis = analyze_paths(list(paths))
    table = Table(title="ActionRepro findings")
    table.add_column("#", justify="right")
    table.add_column("Category")
    table.add_column("Job")
    table.add_column("Step")
    table.add_column("Headline")
    for index, failure in enumerate(analysis.failures, start=1):
        table.add_row(
            str(index),
            failure.category,
            failure.job,
            failure.step,
            failure.headline[:90],
        )
    console.print(table)
    if not analysis.failures:
        console.print("[yellow]No obvious failure marker found.[/yellow]")


@main.command("plan")
@click.argument("paths", nargs=-1, required=True, type=click.Path(exists=True, dir_okay=False))
@click.option("--format", "fmt", type=click.Choice(["md", "json", "comment"]), default="md")
@click.option("--out", type=click.Path(dir_okay=False), help="Output report path.")
def plan_cmd(paths: tuple[str, ...], fmt: str, out: str | None) -> None:
    """Generate a repro plan from one or more logs."""
    analysis = analyze_paths(list(paths))
    if out:
        if fmt == "comment":
            path = Path(out)
            if path.parent != Path("."):
                path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(to_pr_comment(analysis) + "\n", encoding="utf-8")
        else:
            path = write_report(analysis, out, "json" if fmt == "json" else "md")
        console.print(f"[green]Wrote report:[/green] {path}")
        return
    if fmt == "json":
        console.print_json(to_json(analysis))
    elif fmt == "comment":
        console.print(to_pr_comment(analysis))
    else:
        console.print(to_markdown(analysis))


@main.command("compare")
@click.argument("before", type=click.Path(exists=True, dir_okay=False))
@click.argument("after", type=click.Path(exists=True, dir_okay=False))
@click.option("--format", "fmt", type=click.Choice(["md", "json"]), default="md")
def compare_cmd(before: str, after: str, fmt: str) -> None:
    """Diff two CI run logs: what is newly failing, what healed, what is pre-existing."""
    from .analyze import analyze_paths
    from .compare import compare_analyses, to_markdown as cmp_markdown

    cmp_result = compare_analyses(analyze_paths([before]), analyze_paths([after]))
    if fmt == "json":
        console.print_json({
            "new": [f.headline for f in cmp_result.new_failures],
            "fixed": [f.headline for f in cmp_result.fixed_failures],
            "still_failing": [f.headline for f in cmp_result.still_failing],
        })
    else:
        console.print(cmp_markdown(cmp_result))


@main.command("comment")
@click.argument("paths", nargs=-1, required=True, type=click.Path(exists=True, dir_okay=False))
@click.option("--pr", type=int, help="Pull request number for context.")
@click.option("--dry-run/--post", default=True, help="Only print the comment. Posting is disabled.")
def comment_cmd(paths: tuple[str, ...], pr: int | None, dry_run: bool) -> None:
    """Draft a PR comment from the first actionable failure."""
    if not dry_run:
        raise click.ClickException(
            "Posting is intentionally disabled in v0.1. Use --dry-run output."
        )
    analysis = analyze_paths(list(paths))
    heading = f"Draft PR comment for #{pr}" if pr else "Draft PR comment"
    console.print(f"[bold]{heading}[/bold]\n")
    console.print(to_pr_comment(analysis))


if __name__ == "__main__":
    main()
