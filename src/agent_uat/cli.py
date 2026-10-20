"""agent-uat: build UAT test scripts and go/no-go sign-off reports for AI agents."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .scenarios import load_scenarios, to_test_script
from .signoff import (
    apply_defect_url_template,
    evaluate,
    load_results,
    render_html,
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
    g.add_argument("--format", choices=("md", "html", "auto"), default="auto",
                   help="report format (auto: .html out → html, else md)")
    g.add_argument("--strict", action="store_true", help="exit 1 unless the decision is GO")
    g.add_argument("--defect-url-template", metavar="URL",
                   help="link defects without a url to a tracker, e.g. "
                        "https://tracker.example/browse/{id}")
    t = sub.add_parser("trace", help="turn a trace export into a results entry for one run")
    t.add_argument("--trace", required=True, type=Path,
                   help="OTLP/JSON, flat span list, or Langfuse-like observations export")
    t.add_argument("--scenario-id", required=True)
    t.add_argument("--session", help="keep only spans/observations with this session.id")
    t.add_argument("--with-args", action="store_true", help="include tool-call arguments")
    t.add_argument("--format", choices=("auto", "otlp", "langfuse"), default="auto",
                   dest="trace_format",
                   help="trace export format (default: auto-detect)")
    a = p.parse_args(argv)

    if a.cmd == "trace":
        calls = load_tool_calls(a.trace, a.session, fmt=a.trace_format)
        entry = {"scenario_id": a.scenario_id, "actual_tool_calls": [c.name for c in calls]}
        if a.with_args:
            entry["tool_call_details"] = [{"name": c.name, "arguments": c.arguments}
                                          for c in calls]
        print(json.dumps(entry, indent=2))
        return 0
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
        fmt = "html" if a.out and a.out.suffix.lower() == ".html" else "md"
    body = (render_html if fmt == "html" else render_markdown)(ev, data.get("run", {}))
    _emit(body, a.out)
    print(f"decision: {ev.decision}", file=sys.stderr)
    return 1 if a.strict and ev.decision != "GO" else 0


if __name__ == "__main__":
    raise SystemExit(main())
