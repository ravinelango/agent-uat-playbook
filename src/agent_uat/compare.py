"""Compare two JSON sign-off reports (e.g. agent build N vs N+1) scenario by scenario."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

# Higher is better. "not run" sits below pass but is not treated as a regression on its own.
_RANK = {"pass": 3, "not run": 2, "blocked": 1, "fail": 0}


@dataclass
class Change:
    id: str
    title: str
    priority: str
    before: str | None
    after: str | None

    @property
    def kind(self) -> str:
        if self.before is None:
            return "added"
        if self.after is None:
            return "removed"
        if self.before == self.after:
            return "unchanged"
        if self.before == "pass" and self.after in ("fail", "blocked"):
            return "regression"
        if self.after == "pass" and self.before in ("fail", "blocked"):
            return "fixed"
        return "changed"


@dataclass
class Comparison:
    before_decision: str
    after_decision: str
    before_pass_rate: float | None
    after_pass_rate: float | None
    changes: list[Change] = field(default_factory=list)

    def of_kind(self, kind: str) -> list[Change]:
        return [c for c in self.changes if c.kind == kind]

    @property
    def has_regression(self) -> bool:
        return bool(self.of_kind("regression"))


def load_report(path: str | Path) -> dict:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("scenarios"), list):
        raise ValueError(f"{path}: not an agent-uat JSON sign-off report (no 'scenarios' list)")
    for s in data["scenarios"]:
        if not isinstance(s, dict) or "id" not in s or s.get("status") not in _RANK:
            raise ValueError(f"{path}: scenario entry missing id or has an unknown status: {s!r}")
    return data


def compare(before: dict, after: dict) -> Comparison:
    b = {s["id"]: s for s in before["scenarios"]}
    a = {s["id"]: s for s in after["scenarios"]}
    changes = []
    for sid in list(b) + [x for x in a if x not in b]:
        src = a.get(sid) or b[sid]
        changes.append(
            Change(
                id=sid,
                title=src.get("title", ""),
                priority=src.get("priority", ""),
                before=b[sid]["status"] if sid in b else None,
                after=a[sid]["status"] if sid in a else None,
            )
        )
    return Comparison(
        before_decision=before.get("decision", "?"),
        after_decision=after.get("decision", "?"),
        before_pass_rate=before.get("pass_rate"),
        after_pass_rate=after.get("pass_rate"),
        changes=changes,
    )


def _rate(r: float | None) -> str:
    return "n/a" if r is None else f"{r:.0%}"


def render_markdown(c: Comparison, before_label: str, after_label: str) -> str:
    lines = [
        "# UAT comparison",
        "",
        f"- Before: `{before_label}`: **{c.before_decision}**, "
        f"pass rate {_rate(c.before_pass_rate)}",
        f"- After: `{after_label}`: **{c.after_decision}**, pass rate {_rate(c.after_pass_rate)}",
        f"- Regressions (pass → fail/blocked): **{len(c.of_kind('regression'))}**",
        f"- Fixed (fail/blocked → pass): {len(c.of_kind('fixed'))}",
        "",
    ]
    moved = [x for x in c.changes if x.kind != "unchanged"]
    if not moved:
        lines.append("No scenario changed status.")
        return "\n".join(lines) + "\n"
    lines += ["| Scenario | Priority | Before | After | Change |", "|---|---|---|---|---|"]
    order = ["regression", "removed", "changed", "added", "fixed"]
    for x in sorted(moved, key=lambda x: (order.index(x.kind), x.id)):
        lines.append(
            f"| {x.id} {x.title} | {x.priority} | {x.before or '—'} | {x.after or '—'} | {x.kind} |"
        )
    return "\n".join(lines) + "\n"
