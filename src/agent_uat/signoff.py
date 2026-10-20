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
non-critical scenarios, argument checks that could not be verified because the
result has no ``tool_call_details``, or a scenario is unstable across runs.
GO otherwise.
"""

from __future__ import annotations

import html
import json
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import quote

from .scenarios import Scenario

STATUSES = ("pass", "fail", "blocked")
SEVERITIES = ("S1", "S2", "S3", "S4")


@dataclass
class RunStats:
    """Per-scenario multi-run counts for the sign-off report."""

    runs: int = 0
    passed: int = 0
    failed: int = 0
    blocked: int = 0
    pass_rate: float | None = None
    unstable: bool = False

    def summary(self) -> str:
        if self.runs <= 0:
            return "-"
        return f"{self.passed}/{self.runs}"


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
        outcomes = r.get("run_outcomes")
        if outcomes is not None:
            bad = [o for o in outcomes if o not in STATUSES]
            if bad:
                raise ValueError(
                    f"result {r.get('scenario_id')}: run_outcomes must be one of {STATUSES}"
                )
    for d in data.get("defects", []):
        if d.get("severity") not in SEVERITIES:
            raise ValueError(f"defect {d.get('id')}: severity must be one of {SEVERITIES}")
        if "url" in d and not _is_http_url(d["url"]):
            raise ValueError(f"defect {d.get('id')}: url must start with http:// or https://")
    return data


def _is_http_url(value: object) -> bool:
    return isinstance(value, str) and value.startswith(("http://", "https://"))


def apply_defect_url_template(data: dict, template: str | None) -> dict:
    """Give each defect without a ``url`` a tracker link built from ``template``.

    ``template`` holds an ``{id}`` placeholder, e.g. ``https://tracker.example/browse/{id}``.
    Defects that already carry a ``url`` keep it. The data dict is updated in place.
    """
    if not template:
        return data
    if "{id}" not in template or not _is_http_url(template):
        raise ValueError("defect URL template must be an http(s) URL containing {id}")
    for d in data.get("defects", []):
        if not d.get("url"):
            d["url"] = template.replace("{id}", quote(str(d["id"]), safe=""))
    return data


def run_stats(r: dict | None) -> RunStats:
    """Compute multi-run counts for one scenario result.

    Prefer ``run_outcomes`` (one status per attempt). Otherwise use ``runs_passed`` /
    ``runs_total`` and optional ``runs_blocked``; remaining non-passes are treated as
    fails, except when the row status is ``blocked`` and ``runs_blocked`` is omitted
    (then the remainder is blocked).
    """
    if not r:
        return RunStats()
    outcomes = r.get("run_outcomes")
    if outcomes is not None:
        passed = sum(1 for o in outcomes if o == "pass")
        failed = sum(1 for o in outcomes if o == "fail")
        blocked = sum(1 for o in outcomes if o == "blocked")
        runs = len(outcomes)
        rate = passed / runs if runs else None
        return RunStats(runs, passed, failed, blocked, rate, len(set(outcomes)) > 1)

    total = int(r.get("runs_total") or 0)
    passed = int(r.get("runs_passed") or 0)
    if total < 0 or passed < 0 or passed > total:
        raise ValueError(
            f"result {r.get('scenario_id')}: runs_passed/runs_total must be 0 ≤ passed ≤ total"
        )
    if "runs_blocked" in r:
        blocked = int(r["runs_blocked"])
        if blocked < 0 or passed + blocked > total:
            raise ValueError(
                f"result {r.get('scenario_id')}: runs_blocked inconsistent with runs_total"
            )
        failed = total - passed - blocked
    elif r.get("status") == "blocked" and total:
        blocked = total - passed
        failed = 0
    else:
        blocked = 0
        failed = total - passed
    rate = passed / total if total else None
    unstable = total > 1 and (failed > 0 or blocked > 0) and passed > 0
    # also unstable if mixed fail+blocked with no passes
    if total > 1 and failed > 0 and blocked > 0:
        unstable = True
    return RunStats(total, passed, failed, blocked, rate, unstable)


def _runs(r: dict | None) -> str:
    return run_stats(r).summary()


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
        stats = run_stats(r)

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
        if stats.unstable:
            parts = []
            if stats.passed:
                parts.append(f"{stats.passed} pass")
            if stats.failed:
                parts.append(f"{stats.failed} fail")
            if stats.blocked:
                parts.append(f"{stats.blocked} blocked")
            conditions.append(
                f"Scenario {s.id} is unstable across runs ({' / '.join(parts)})"
            )

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
        rows.append({
            "id": s.id, "title": s.title, "priority": s.priority, "status": status,
            "runs": stats.summary(), "stats": stats,
            "defects": ", ".join(r.get("defects", [])) if r else "",
        })

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


def _fmt_rate(rate: float | None) -> str:
    return "-" if rate is None else f"{rate:.0%}"


def _md_defect_id(d: dict) -> str:
    return f"[{d['id']}]({d['url']})" if d.get("url") else str(d["id"])


def _html_defect_id(d: dict) -> str:
    ident = html.escape(str(d["id"]))
    if d.get("url"):
        return f"<a href='{html.escape(d['url'], quote=True)}'>{ident}</a>"
    return ident


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
    lines += ["", "## Multi-run statistics", "",
              "Per-scenario attempt counts. A scenario is **unstable** when runs disagree "
              "(pass vs fail/blocked). Any S1 occurrence is still S1.", "",
              "| Scenario | Runs | Pass | Fail | Blocked | Pass rate | Stable |",
              "|---|---|---|---|---|---|---|"]
    for r in ev.rows:
        st: RunStats = r["stats"]
        if st.runs <= 0:
            lines.append(f"| {r['id']} | - | - | - | - | - | - |")
        else:
            stable = "no" if st.unstable else "yes"
            lines.append(
                f"| {r['id']} | {st.runs} | {st.passed} | {st.failed} | {st.blocked} | "
                f"{_fmt_rate(st.pass_rate)} | {stable} |"
            )
    lines += ["", "## Open defects", ""]
    if ev.open_defects:
        lines += ["| ID | Severity | Category | Scenario | Title |", "|---|---|---|---|---|"]
        lines += [f"| {_md_defect_id(d)} | {d['severity']} | {d.get('category', '-')} | "
                  f"{d.get('scenario_id', '-')} | {d.get('title', '')} |" for d in ev.open_defects]
    else:
        lines.append("None.")
    lines += ["", "## Sign-off", "",
              "| Role | Name | Decision | Date |", "|---|---|---|---|",
              "| Business owner | | | |", "| QA / UAT lead | | | |", "| Engineering lead | | | |",
              "", "_The generated decision is a recommendation from the rules above; "
              "the accountable owners make the release call._", ""]
    return "\n".join(lines)


_CSS = (
    "body{font-family:system-ui,sans-serif;max-width:960px;margin:2em auto;color:#1b1f24;"
    "line-height:1.45}"
    "h1,h2,h3{margin-top:1.4em}"
    "table{border-collapse:collapse;width:100%;margin:1em 0}"
    "th,td{border:1px solid #d0d7de;padding:6px 8px;text-align:left;vertical-align:top}"
    "th{background:#f6f8fa}"
    ".banner{background:#fff8c5;border:1px solid #d4a72c;padding:8px 12px}"
    ".meta{margin:.5em 0 1em}"
    ".GO{color:#1a7f37;font-weight:700}"
    ".NO-GO{color:#cf222e;font-weight:700}"
    ".GO.WITH.CONDITIONS{color:#9a6700;font-weight:700}"
    ".sign{margin-top:2em;border-top:1px solid #d0d7de;padding-top:1em}"
    "ul{padding-left:1.2em}"
    "@media print{body{margin:.5in}th{background:#eee}"
    ".banner{-webkit-print-color-adjust:exact;print-color-adjust:exact}}"
)


def _decision_span(decision: str) -> str:
    cls = html.escape(decision.replace(" ", "."))
    return f"<span class='{cls}'>{html.escape(decision)}</span>"


def render_html(ev: Evaluation, run: dict) -> str:
    """Self-contained, print-friendly HTML go/no-go sign-off (no external assets)."""
    e = html.escape
    parts = [
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>",
        "<title>UAT go/no-go sign-off</title>",
        f"<style>{_CSS}</style></head><body>",
        "<h1>UAT go/no-go sign-off</h1>",
    ]
    if run.get("label"):
        parts.append(f"<p class='banner'><strong>{e(str(run['label']))}</strong></p>")
    meta = [(k.replace("_", " ").capitalize(), v)
            for k, v in run.items() if k != "label"]
    if meta:
        parts.append("<ul class='meta'>")
        parts += [f"<li>{e(k)}: {e(str(v))}</li>" for k, v in meta]
        parts.append("</ul>")
    parts.append(f"<h2>Decision: {_decision_span(ev.decision)}</h2>")
    if ev.reasons:
        parts.append("<h3>Blocking reasons</h3><ul>")
        parts += [f"<li>{e(x)}</li>" for x in ev.reasons]
        parts.append("</ul>")
    if ev.conditions:
        parts.append("<h3>Conditions</h3><ul>")
        parts += [f"<li>{e(x)}</li>" for x in ev.conditions]
        parts.append("</ul>")
    c = ev.counts
    parts.append(
        f"<h2>Summary</h2><p>Pass rate {ev.pass_rate:.0%} · pass {c['pass']} · "
        f"fail {c['fail']} · blocked {c['blocked']} · not run {c['not run']}</p>")
    parts.append("<h2>Scenario results</h2><table><tr>"
                 "<th>Scenario</th><th>Title</th><th>Priority</th><th>Status</th>"
                 "<th>Runs passed</th><th>Defects</th></tr>")
    for r in ev.rows:
        parts.append(
            f"<tr><td>{e(r['id'])}</td><td>{e(r['title'])}</td><td>{e(r['priority'])}</td>"
            f"<td>{e(r['status'].upper())}</td><td>{e(r['runs'])}</td>"
            f"<td>{e(r['defects'] or '-')}</td></tr>")
    parts.append("</table>")
    parts.append(
        "<h2>Multi-run statistics</h2>"
        "<p>Per-scenario attempt counts. A scenario is <strong>unstable</strong> when runs "
        "disagree (pass vs fail/blocked). Any S1 occurrence is still S1.</p>"
        "<table><tr><th>Scenario</th><th>Runs</th><th>Pass</th><th>Fail</th>"
        "<th>Blocked</th><th>Pass rate</th><th>Stable</th></tr>")
    for r in ev.rows:
        st: RunStats = r["stats"]
        if st.runs <= 0:
            parts.append(f"<tr><td>{e(r['id'])}</td><td>-</td><td>-</td><td>-</td>"
                         "<td>-</td><td>-</td><td>-</td></tr>")
        else:
            stable = "no" if st.unstable else "yes"
            parts.append(
                f"<tr><td>{e(r['id'])}</td><td>{st.runs}</td><td>{st.passed}</td>"
                f"<td>{st.failed}</td><td>{st.blocked}</td>"
                f"<td>{e(_fmt_rate(st.pass_rate))}</td><td>{stable}</td></tr>")
    parts.append("</table><h2>Open defects</h2>")
    if ev.open_defects:
        parts.append("<table><tr><th>ID</th><th>Severity</th><th>Category</th>"
                     "<th>Scenario</th><th>Title</th></tr>")
        for d in ev.open_defects:
            parts.append(
                f"<tr><td>{_html_defect_id(d)}</td><td>{e(d['severity'])}</td>"
                f"<td>{e(str(d.get('category', '-')))}</td>"
                f"<td>{e(str(d.get('scenario_id', '-')))}</td>"
                f"<td>{e(str(d.get('title', '')))}</td></tr>")
        parts.append("</table>")
    else:
        parts.append("<p>None.</p>")
    parts.append(
        "<div class='sign'><h2>Sign-off</h2>"
        "<table><tr><th>Role</th><th>Name</th><th>Decision</th><th>Date</th></tr>"
        "<tr><td>Business owner</td><td></td><td></td><td></td></tr>"
        "<tr><td>QA / UAT lead</td><td></td><td></td><td></td></tr>"
        "<tr><td>Engineering lead</td><td></td><td></td><td></td></tr></table>"
        "<p><em>The generated decision is a recommendation from the rules above; "
        "the accountable owners make the release call.</em></p></div>"
        "</body></html>")
    return "\n".join(parts) + "\n"
