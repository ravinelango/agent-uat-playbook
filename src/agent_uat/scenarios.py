"""Scenario-based acceptance criteria for AI agents.

A scenario is Given/When/Then plus what the agent must (and must not) do with tools,
and the guardrails a business user checks. Stored as JSON (one file = list of scenarios).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

PRIORITIES = ("critical", "high", "medium", "low")


@dataclass(frozen=True)
class Scenario:
    id: str
    title: str
    priority: str
    given: list[str]
    when: str
    then: list[str]
    expected_tool_calls: list[str] = field(default_factory=list)
    forbidden_tool_calls: list[str] = field(default_factory=list)
    guardrails: list[str] = field(default_factory=list)
    ordered_tool_calls: bool = False
    tool_argument_checks: list[dict] = field(default_factory=list)


def _parse_arg_checks(sid: str, raw) -> list[dict]:
    """``[{"tool": "lookup_order", "args": {"order_id": "A1001"}}, ...]``"""
    checks = []
    for c in raw or []:
        if not isinstance(c, dict) or not c.get("tool") or not isinstance(c.get("args"), dict) \
                or not c["args"]:
            raise ValueError(f"scenario {sid}: each tool_argument_checks entry needs "
                             "'tool' and a non-empty 'args' object")
        checks.append({"tool": str(c["tool"]), "args": dict(c["args"])})
    return checks


def _as_list(v) -> list[str]:
    if v is None:
        return []
    return [str(x) for x in (v if isinstance(v, list) else [v])]


def parse_scenario(d: dict) -> Scenario:
    if not isinstance(d, dict):
        raise ValueError(f"each scenario must be a JSON object, got {type(d).__name__}")
    missing = [k for k in ("id", "title", "given", "when", "then") if not d.get(k)]
    if missing:
        raise ValueError(f"scenario {d.get('id', '?')}: missing {', '.join(missing)}")
    priority = str(d.get("priority", "medium")).lower()
    if priority not in PRIORITIES:
        raise ValueError(f"scenario {d['id']}: priority must be one of {PRIORITIES}")
    s = Scenario(
        id=str(d["id"]), title=str(d["title"]), priority=priority,
        given=_as_list(d["given"]), when=str(d["when"]), then=_as_list(d["then"]),
        expected_tool_calls=_as_list(d.get("expected_tool_calls")),
        forbidden_tool_calls=_as_list(d.get("forbidden_tool_calls")),
        guardrails=_as_list(d.get("guardrails")),
        ordered_tool_calls=bool(d.get("ordered_tool_calls", False)),
        tool_argument_checks=_parse_arg_checks(str(d["id"]), d.get("tool_argument_checks")),
    )
    if s.ordered_tool_calls and len(s.expected_tool_calls) < 2:
        raise ValueError(f"scenario {s.id}: ordered_tool_calls needs 2+ expected_tool_calls")
    banned = sorted({c["tool"] for c in s.tool_argument_checks} & set(s.forbidden_tool_calls))
    if banned:
        raise ValueError(f"scenario {s.id}: argument checks on forbidden tool(s): {banned}")
    overlap = set(s.expected_tool_calls) & set(s.forbidden_tool_calls)
    if overlap:
        raise ValueError(f"scenario {s.id}: tool both expected and forbidden: {sorted(overlap)}")
    return s


def load_scenarios(path: str | Path) -> list[Scenario]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    items = data.get("scenarios") if isinstance(data, dict) else data
    if not isinstance(items, list):
        raise ValueError(f"{path}: expected a list of scenarios or an object with a "
                         "'scenarios' list")
    out = [parse_scenario(d) for d in items]
    ids = [s.id for s in out]
    dupes = sorted({i for i in ids if ids.count(i) > 1})
    if dupes:
        raise ValueError(f"duplicate scenario ids: {dupes}")
    return out


def _codes(items: list[str]) -> str:
    return ", ".join(f"`{t}`" for t in items)


def to_test_script(scenarios: list[Scenario]) -> str:
    """Render a business-user test script (markdown) from scenarios."""
    lines = ["# UAT test script", "",
             "Tester: __________  Date: ________  Agent build/version: __________", ""]
    for s in scenarios:
        lines += [f"## {s.id}: {s.title} ({s.priority})", "", "**Given**"]
        lines += [f"- {g}" for g in s.given]
        lines += ["", f"**When** {s.when}", "", "**Then** (check each)"]
        lines += [f"- [ ] {t}" for t in s.then]
        if s.expected_tool_calls:
            joiner = " → " if s.ordered_tool_calls else ", "
            label = "in this order" if s.ordered_tool_calls else ""
            calls = joiner.join(f"`{t}`" for t in s.expected_tool_calls)
            lines += ["", f"**Agent should call{' ' + label if label else ''}:** {calls}"]
        for c in s.tool_argument_checks:
            args = ", ".join(f"{k}={v!r}" for k, v in c["args"].items())
            lines += [f"- [ ] `{c['tool']}` called with {args}"]
        if s.forbidden_tool_calls:
            lines += ["", "**Agent must NOT call:** " + _codes(s.forbidden_tool_calls)]
        if s.guardrails:
            lines += ["", "**Guardrails**"] + [f"- [ ] {g}" for g in s.guardrails]
        lines += ["", "Result: ☐ Pass ☐ Fail ☐ Blocked   Defect ID(s): ________", "",
                  "Notes: ______________________________________", ""]
    return "\n".join(lines)
