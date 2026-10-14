"""Pull the agent's tool calls out of an OpenTelemetry trace export.

Supports two shapes:

* OTLP/JSON as written by the OpenTelemetry Collector file exporter
  (``resourceSpans[].scopeSpans[].spans[]`` with ``attributes`` as key/value lists).
* A flat list of spans (``{"spans": [...]}`` or a bare list) where ``attributes``
  is a plain dict. Many tracing tools can export this shape.

A span counts as a tool call when it follows the OpenTelemetry GenAI semantic
conventions: ``gen_ai.operation.name == "execute_tool"`` with the tool name in
``gen_ai.tool.name``. Calls are returned in start-time order so order checks work.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

OP_KEY = "gen_ai.operation.name"
TOOL_KEY = "gen_ai.tool.name"
ARGS_KEY = "gen_ai.tool.call.arguments"
ID_KEY = "gen_ai.tool.call.id"
SESSION_KEYS = ("session.id", "gen_ai.conversation.id")


@dataclass(frozen=True)
class ToolCall:
    name: str
    start_ns: int
    trace_id: str = ""
    call_id: str = ""
    arguments: dict = field(default_factory=dict)


def _otlp_value(v: dict):
    if not isinstance(v, dict):
        return v
    for k in ("stringValue", "boolValue", "doubleValue"):
        if k in v:
            return v[k]
    if "intValue" in v:
        return int(v["intValue"])
    if "arrayValue" in v:
        return [_otlp_value(x) for x in v["arrayValue"].get("values", [])]
    return None


def _attrs(span: dict) -> dict:
    a = span.get("attributes") or {}
    if isinstance(a, list):
        return {kv.get("key"): _otlp_value(kv.get("value", {})) for kv in a}
    return dict(a)


def _iter_spans(data):
    if isinstance(data, dict) and "resourceSpans" in data:
        for rs in data["resourceSpans"]:
            for ss in rs.get("scopeSpans", []):
                yield from ss.get("spans", [])
        return
    spans = data.get("spans", []) if isinstance(data, dict) else data
    yield from spans


def _parse_args(raw) -> dict:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str) and raw.strip():
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return {"_raw": raw}
        return parsed if isinstance(parsed, dict) else {"_value": parsed}
    return {}


def extract_tool_calls(data, session: str | None = None) -> list[ToolCall]:
    """Return tool calls from a trace export, oldest first.

    ``session`` keeps only spans whose ``session.id`` (or ``gen_ai.conversation.id``)
    matches, so one export holding many test runs can be split per scenario run.
    """
    calls = []
    for span in _iter_spans(data):
        a = _attrs(span)
        if a.get(OP_KEY) != "execute_tool" or not a.get(TOOL_KEY):
            continue
        if session is not None and session not in {str(a.get(k)) for k in SESSION_KEYS}:
            continue
        calls.append(ToolCall(
            name=str(a[TOOL_KEY]),
            start_ns=int(span.get("startTimeUnixNano", 0) or 0),
            trace_id=str(span.get("traceId", "")),
            call_id=str(a.get(ID_KEY, "")),
            arguments=_parse_args(a.get(ARGS_KEY)),
        ))
    return sorted(calls, key=lambda c: c.start_ns)


def load_tool_calls(path: str | Path, session: str | None = None) -> list[ToolCall]:
    return extract_tool_calls(json.loads(Path(path).read_text(encoding="utf-8")), session)
