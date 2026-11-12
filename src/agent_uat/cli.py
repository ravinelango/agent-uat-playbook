"""agent-uat: build UAT test scripts and go/no-go sign-off reports for AI agents."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .compare import compare, load_report, to_dict
from .compare import render_markdown as render_compare
from .scenarios import load_scenarios, to_test_script
from .signoff import (
    apply_defect_url_template,
    evaluate,
    load_results,
    render_html,
    render_json,
    render_markdown,
)
from .traces import load_tool_calls


def _emit(text: str, out: Path | None) -> None:
    if out:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
        print(f"wrote {out}")
    else:
        sys.stdout.write(text)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="agent-uat", description=__doc__)
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)
    v = sub.add_parser("validate", help="check a scenarios file")
    v.add_argument("--scenarios", required=True, type=Path)
    s = sub.add_parser("script", help="render a business-user test script")
    s.add_argument("--scenarios", required=True, type=Path)
    s.add_argument("--out", type=Path)
    g = sub.add_parser("signoff", help="evaluate results and write a go/no-go report")
    g.add_argument("--scenarios", required=True, type=Path)
    g.add_argument("--results", required=True, type=Path)
    g.add_argument("--min-pass-rate", type=float, default=0.9)
    g.add_argument("--out", type=Path)
    g.add_argument(
        "--format",
        choices=("md", "html", "json", "auto"),
        default="auto",
        help="report format (auto: .html/.json out → that format, else md)",
    )
    g.add_argument("--strict", action="store_true", help="exit 1 unless the decision is GO")
    g.add_argument(
        "--defect-url-template",
        metavar="URL",
        help="link defects without a url to a tracker, e.g. https://tracker.example/browse/{id}",
    )
    t = sub.add_parser("trace", help="turn a trace export into a results entry for one run")
    t.add_argument(
        "--trace",
        required=True,
        type=Path,
        help="OTLP/JSON, flat span list, or Langfuse-like observations export",
    )
    t.add_argument("--scenario-id", required=True)
    t.add_argument("--session", help="keep only spans/observations with this session.id")
    t.add_argument("--with-args", action="store_true", help="include tool-call arguments")
    t.add_argument(
        "--format",
        choices=("auto", "otlp", "langfuse"),
        default="auto",
        dest="trace_format",
        help="trace export format (default: auto-detect)",
    )
    c = sub.add_parser("compare", help="diff two JSON sign-off reports (e.g. build N vs N+1)")
    c.add_argument("--before", required=True, type=Path, help="earlier signoff --format json")
    c.add_argument("--after", required=True, type=Path, help="later signoff --format json")
    c.add_argument("--out", type=Path)
    c.add_argument(
        "--format",
        choices=("md", "json"),
        default=None,
        dest="compare_format",
        help="output format (default: md, or json when --out ends in .json)",
    )
    c.add_argument(
        "--strict", action="store_true", help="exit 1 if any scenario went pass → fail/blocked"
    )
    a = p.parse_args(argv)

    for flag in ("scenarios", "results", "trace", "before", "after"):
        path = getattr(a, flag, None)
        if path is not None and not path.is_file():
            print(f"agent-uat: error: no such file for --{flag}: {path}", file=sys.stderr)
            return 2

    if a.cmd == "trace":
        calls = load_tool_calls(a.trace, a.session, fmt=a.trace_format)
        entry = {"scenario_id": a.scenario_id, "actual_tool_calls": [c.name for c in calls]}
        if a.with_args:
            entry["tool_call_details"] = [{"name": c.name, "arguments": c.arguments} for c in calls]
        print(json.dumps(entry, indent=2))
        return 0
    if a.cmd == "compare":
        try:
            cmp = compare(load_report(a.before), load_report(a.after))
        except ValueError as e:
            print(f"agent-uat: error: {e}", file=sys.stderr)
            return 2
        fmt = a.compare_format or (
            "json" if a.out is not None and a.out.suffix.lower() == ".json" else "md"
        )
        if fmt == "json":
            text = json.dumps(to_dict(cmp, str(a.before), str(a.after)), indent=2) + "\n"
        else:
            text = render_compare(cmp, str(a.before), str(a.after))
        _emit(text, a.out)
        print(f"regressions: {len(cmp.of_kind('regression'))}", file=sys.stderr)
        return 1 if a.strict and cmp.has_regression else 0
    scenarios = load_scenarios(a.scenarios)
    if a.cmd == "validate":
        print(f"OK: {len(scenarios)} scenarios")
        return 0
    if a.cmd == "script":
        _emit(to_test_script(scenarios), a.out)
        return 0
    data = apply_defect_url_template(load_results(a.results), a.defect_url_template)
    ev = evaluate(scenarios, data, a.min_pass_rate)
    fmt = a.format
    if fmt == "auto":
        suffix = a.out.suffix.lower() if a.out else ""
        if suffix == ".html":
            fmt = "html"
        elif suffix == ".json":
            fmt = "json"
        else:
            fmt = "md"
    render = {"html": render_html, "json": render_json, "md": render_markdown}[fmt]
    body = render(ev, data.get("run", {}))
    _emit(body, a.out)
    print(f"decision: {ev.decision}", file=sys.stderr)
    return 1 if a.strict and ev.decision != "GO" else 0


if __name__ == "__main__":
    raise SystemExit(main())
