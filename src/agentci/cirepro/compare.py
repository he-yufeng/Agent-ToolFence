"""Regression diff between two CI runs: what is newly failing and what healed.

The daily triage question is never "is it red" but "did I break it". Comparing
a run against its previous green (or baseline) run turns that into data:
failures present in both are pre-existing noise, the new ones are yours.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .models import Analysis, Failure

_NUM = re.compile(r"\d+(?:\.\d+)?")


def _key(f: Failure) -> str:
    """Identity of a failure across runs: same job/step/category/headline, with
    numbers blanked out so durations and counts do not fork the identity."""
    headline = _NUM.sub("#", f.headline)
    return f"{f.job}|{f.step}|{f.category}|{headline}"


@dataclass(slots=True)
class Comparison:
    before_paths: list[str]
    after_paths: list[str]
    new_failures: list[Failure] = field(default_factory=list)
    fixed_failures: list[Failure] = field(default_factory=list)
    still_failing: list[Failure] = field(default_factory=list)


def compare_analyses(before: Analysis, after: Analysis) -> Comparison:
    """Diff two analyzed runs: after-minus-before, before-minus-after, overlap."""
    before_keys = {_key(f) for f in before.failures}
    after_keys = {_key(f) for f in after.failures}
    return Comparison(
        before_paths=[str(p) for p in before.paths],
        after_paths=[str(p) for p in after.paths],
        new_failures=[f for f in after.failures if _key(f) not in before_keys],
        fixed_failures=[f for f in before.failures if _key(f) not in after_keys],
        still_failing=[f for f in after.failures if _key(f) in before_keys],
    )


def to_markdown(cmp: Comparison) -> str:
    lines = ["# CI run comparison", ""]
    lines.append(f"- before: `{', '.join(cmp.before_paths)}`")
    lines.append(f"- after: `{', '.join(cmp.after_paths)}`")
    lines.append(
        f"- new: {len(cmp.new_failures)} · fixed: {len(cmp.fixed_failures)} · still failing: {len(cmp.still_failing)}"
    )
    for title, failures in (
        ("## New failures", cmp.new_failures),
        ("## Fixed", cmp.fixed_failures),
        ("## Still failing (pre-existing)", cmp.still_failing),
    ):
        lines += ["", title]
        if not failures:
            lines.append("- none")
            continue
        for f in failures:
            lines.append(f"- **{f.job} / {f.step}** ({f.category}): {f.headline}")
    return "\n".join(lines)
