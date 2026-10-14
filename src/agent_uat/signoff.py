"""Evaluate UAT results against scenarios and produce a go/no-go decision.

Decision rules (v0.1, documented in the README):
NO-GO if any of
  - a critical scenario failed, was blocked, or has no result
  - the agent called a forbidden tool in any scenario
  - any guardrail violation was recorded
  - any S1 or S2 defect is still open
  - overall pass rate < min_pass_rate
  - a critical scenario called its expected tools out of order (``ordered_tool_calls``)
    or with the wrong arguments (``tool_argument_checks``)
GO WITH CONDITIONS if not NO-GO but there are open S3 defects, untested non-critical
scenarios, expected tool calls that were missed, order/argument mismatches on
non-critical scenarios, or argument checks that could not be verified because the
result has no ``tool_call_details``.
GO otherwise.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from .scenarios import Scenario

STATUSES = ("pass", "fail", "blocked")
SEVERITIES = ("S1", "S2", "S3", "S4")


@dataclass
class Evaluation:
    decision: str
    reasons: list[str]
    conditions: list[str]
    pass_rate: float
    counts: dict[str, int]
    rows: list[dict] = field(default_factory=list)
    open_defects: list[dict] = field(default_factory=list)


def load_results(path: str | Path) -> dict:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    for r in data.get("results", []):
        if r.get("status") not in STATUSES:
            raise ValueError(f"result {r.get('scenario_id')}: status must be one of {STATUSES}")
    for d in data.get("defects", []):
        if d.get("severity") not in SEVERITIES:
            raise ValueError(f"defect {d.get('id')}: severity must be one of {SEVERITIES}")
    return data


def _runs(r: dict | None) -> str:
    return f"{r.get('runs_passed', '-')}/{r.get('runs_total', '-')}" if r else "-"


def in_order(expected: list[str], actual: list[str]) -> bool:
    """True if ``expected`` appears in ``actual`` as a subsequence (other calls may sit between)."""
    it = iter(actual)
    return all(any(a == e for a in it) for e in expected)


def _args_match(want: dict, got: dict) -> bool:
    return all(k in got and got[k] == v for k, v in want.items())


def argument_mismatches(checks: list[dict], details: list[dict]) -> list[str]:
    """Describe each check where the tool was called but never with the expected arguments.

    A check on a tool that was not called at all is left to the missed-call rule.
    """
    out = []
    for c in checks:
        calls = [d.get("arguments") or {} for d in details if d.get("name") == c["tool"]]
        if calls and not any(_args_match(c["args"], got) for got in calls):
            want = ", ".join(f"{k}={v!r}" for k, v in c["args"].items())
            out.append(f"{c['tool']} not called with {want}")
    return out


def evaluate(scenarios: list[Scenario], data: dict, min_pass_rate: float = 0.9) -> Evaluation:
    by_id = {r["scenario_id"]: r for r in data.get("results", [])}
    known = {s.id for s in scenarios}
    reasons: list[str] = []
    conditions: list[str] = []
    counts = {"pass": 0, "fail": 0, "blocked": 0, "not run": 0}
    rows = []

    for extra in sorted(set(by_id) - known):
        conditions.append(f"Result {extra} does not match any scenario")

    for s in scenarios:
        r = by_id.get(s.id)
        status = r["status"] if r else "not run"
        counts[status] += 1
        actual = set(r.get("actual_tool_calls", [])) if r else set()
        forbidden_hit = sorted(actual & set(s.forbidden_tool_calls))
        missed = sorted(set(s.expected_tool_calls) - actual) if r else []
        violations = r.get("guardrail_violations", []) if r else []

        if s.priority == "critical" and status != "pass":
            reasons.append(f"Critical scenario {s.id} is {status.upper()}")
        elif status == "not run":
            conditions.append(f"Scenario {s.id} ({s.priority}) was not run")
        if forbidden_hit:
            reasons.append(f"Scenario {s.id}: agent called forbidden tool(s) {forbidden_hit}")
        for v in violations:
            reasons.append(f"Scenario {s.id}: guardrail violation: {v}")
        if missed and status == "pass":
            conditions.append(f"Scenario {s.id} passed but expected tool(s) not called: {missed}")

        problems = []
        if r and s.ordered_tool_calls and not missed and not in_order(
                s.expected_tool_calls, list(r.get("actual_tool_calls", []))):
            problems.append("expected tools called out of order "
                            f"(expected {' -> '.join(s.expected_tool_calls)})")
        if r and s.tool_argument_checks:
            details = r.get("tool_call_details")
            if details is None:
                conditions.append(f"Scenario {s.id}: argument checks not verified "
                                  "(no tool_call_details in result)")
            else:
                problems += argument_mismatches(s.tool_argument_checks, details)
        for msg in problems:
            target = reasons if s.priority == "critical" else conditions
            target.append(f"Scenario {s.id}: {msg}")
        rows.append({"id": s.id, "title": s.title, "priority": s.priority, "status": status,
                     "runs": _runs(r),
                     "defects": ", ".join(r.get("defects", [])) if r else ""})

    open_defects = [d for d in data.get("defects", []) if d.get("status", "open") == "open"]
    for d in open_defects:
        if d["severity"] in ("S1", "S2"):
            reasons.append(f"Open {d['severity']} defect {d['id']}: {d.get('title', '')}".rstrip())
        elif d["severity"] == "S3":
            conditions.append(f"Open S3 defect {d['id']} needs a fix plan")

    executed = len(scenarios)
    pass_rate = counts["pass"] / executed if executed else 0.0
    if pass_rate < min_pass_rate:
        reasons.append(f"Pass rate {pass_rate:.0%} is below the {min_pass_rate:.0%} threshold")

    decision = "NO-GO" if reasons else ("GO WITH CONDITIONS" if conditions else "GO")
    return Evaluation(decision, reasons, conditions, pass_rate, counts, rows, open_defects)


def render_markdown(ev: Evaluation, run: dict) -> str:
    lines = ["# UAT go/no-go sign-off", ""]
    if run.get("label"):
        lines += [f"> **{run['label']}**", ""]
    lines += [f"- {k.replace('_', ' ').capitalize()}: {v}" for k, v in run.items() if k != "label"]
    lines += ["", f"## Decision: **{ev.decision}**", ""]
    if ev.reasons:
        lines += ["### Blocking reasons", ""] + [f"- {x}" for x in ev.reasons] + [""]
    if ev.conditions:
        lines += ["### Conditions", ""] + [f"- {x}" for x in ev.conditions] + [""]
    c = ev.counts
    lines += ["## Summary", "",
              f"Pass rate {ev.pass_rate:.0%} · pass {c['pass']} · fail {c['fail']} · "
              f"blocked {c['blocked']} · not run {c['not run']}", "",
              "## Scenario results", "",
              "| Scenario | Title | Priority | Status | Runs passed | Defects |",
              "|---|---|---|---|---|---|"]
    lines += [f"| {r['id']} | {r['title']} | {r['priority']} | {r['status'].upper()} | "
              f"{r['runs']} | {r['defects'] or '-'} |" for r in ev.rows]
    lines += ["", "## Open defects", ""]
    if ev.open_defects:
        lines += ["| ID | Severity | Category | Scenario | Title |", "|---|---|---|---|---|"]
        lines += [f"| {d['id']} | {d['severity']} | {d.get('category', '-')} | "
                  f"{d.get('scenario_id', '-')} | {d.get('title', '')} |" for d in ev.open_defects]
    else:
        lines.append("None.")
    lines += ["", "## Sign-off", "",
              "| Role | Name | Decision | Date |", "|---|---|---|---|",
              "| Business owner | | | |", "| QA / UAT lead | | | |", "| Engineering lead | | | |",
              "", "_The generated decision is a recommendation from the rules above; "
              "the accountable owners make the release call._", ""]
    return "\n".join(lines)
