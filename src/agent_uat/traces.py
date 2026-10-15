"""Pull the agent's tool calls out of an OpenTelemetry or Langfuse-like export.

Supports three shapes:

* OTLP/JSON as written by the OpenTelemetry Collector file exporter
  (``resourceSpans[].scopeSpans[].spans[]`` with ``attributes`` as key/value lists).
* A flat list of spans (``{"spans": [...]}`` or a bare list) where ``attributes``
  is a plain dict. Many tracing tools can export this shape.
* A **Langfuse-like** JSON export with an ``observations`` array (and optional
  ``traces``). Tool observations are those with ``type`` ``TOOL``/``tool``,
  ``metadata["langfuse.observation.type"] == "tool"``, or GenAI
  ``execute_tool`` metadata. This parser targets a synthetic / simplified export
  shape suitable for fixtures — not every Langfuse UI dump variant.

A span/observation counts as a tool call when it follows the OpenTelemetry GenAI
semantic conventions (``gen_ai.operation.name == "execute_tool"``) or the Langfuse
tool markers above. Calls are returned in start-time order so order checks work.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
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


def _iso_to_ns(value) -> int:
    if value is None or value == "":
        return 0
    if isinstance(value, (int, float)):
        # Already ns or ms — treat large ints as ns, small as ms.
        v = int(value)
        return v if v > 10_000_000_000_000 else v * 1_000_000
    s = str(value).strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        return 0
    return int(dt.timestamp() * 1_000_000_000)


def _meta(obs: dict) -> dict:
    m = obs.get("metadata") or {}
    return dict(m) if isinstance(m, dict) else {}


def _is_langfuse_tool(obs: dict, meta: dict) -> bool:
    t = str(obs.get("type") or "").lower()
    if t == "tool":
        return True
    if str(meta.get("langfuse.observation.type") or "").lower() == "tool":
        return True
    if meta.get(OP_KEY) == "execute_tool":
        return True
    return False


def _iter_langfuse_observations(data):
    if isinstance(data, list):
        yield from data
        return
    if not isinstance(data, dict):
        return
    if "observations" in data:
        yield from data.get("observations") or []
        return
    # Nested under traces[].observations
    for tr in data.get("traces") or []:
        if isinstance(tr, dict):
            yield from tr.get("observations") or []


def extract_tool_calls_langfuse(data, session: str | None = None) -> list[ToolCall]:
    """Return tool calls from a Langfuse-like observations export, oldest first."""
    calls: list[ToolCall] = []
    for obs in _iter_langfuse_observations(data):
        if not isinstance(obs, dict):
            continue
        meta = _meta(obs)
        if not _is_langfuse_tool(obs, meta):
            continue
        name = meta.get(TOOL_KEY) or obs.get("name")
        if not name:
            continue
        sess_vals = {str(meta.get(k)) for k in SESSION_KEYS}
        if obs.get("sessionId") is not None:
            sess_vals.add(str(obs.get("sessionId")))
        if session is not None and session not in sess_vals:
            continue
        start = obs.get("startTimeUnixNano")
        if start is None:
            start = _iso_to_ns(obs.get("startTime"))
        else:
            start = int(start)
        args = _parse_args(meta.get(ARGS_KEY) if ARGS_KEY in meta else obs.get("input"))
        calls.append(
            ToolCall(
                name=str(name),
                start_ns=int(start or 0),
                trace_id=str(obs.get("traceId") or obs.get("trace_id") or ""),
                call_id=str(meta.get(ID_KEY) or obs.get("id") or ""),
                arguments=args,
            )
        )
    return sorted(calls, key=lambda c: c.start_ns)


def extract_tool_calls_otlp(data, session: str | None = None) -> list[ToolCall]:
    """Return tool calls from an OTLP/JSON or flat span export, oldest first."""
    calls = []
    for span in _iter_spans(data):
        a = _attrs(span)
        if a.get(OP_KEY) != "execute_tool" or not a.get(TOOL_KEY):
            continue
        if session is not None and session not in {str(a.get(k)) for k in SESSION_KEYS}:
            continue
        calls.append(
            ToolCall(
                name=str(a[TOOL_KEY]),
                start_ns=int(span.get("startTimeUnixNano", 0) or 0),
                trace_id=str(span.get("traceId", "")),
                call_id=str(a.get(ID_KEY, "")),
                arguments=_parse_args(a.get(ARGS_KEY)),
            )
        )
    return sorted(calls, key=lambda c: c.start_ns)


def detect_trace_format(data) -> str:
    """Return ``langfuse`` or ``otlp`` for a loaded export."""
    if isinstance(data, dict) and (
        "observations" in data
        or (isinstance(data.get("traces"), list) and data.get("traces"))
    ):
        # Prefer langfuse when observations exist; a traces list alone is ambiguous
        # but our synthetic Langfuse fixture always includes observations.
        if "observations" in data:
            return "langfuse"
        for tr in data.get("traces") or []:
            if isinstance(tr, dict) and "observations" in tr:
                return "langfuse"
    return "otlp"


def extract_tool_calls(
    data,
    session: str | None = None,
    *,
    fmt: str = "auto",
) -> list[ToolCall]:
    """Return tool calls from a trace export, oldest first.

    ``session`` keeps only spans/observations whose session id matches.
    ``fmt`` is ``auto``, ``otlp``, or ``langfuse``.
    """
    if fmt == "auto":
        fmt = detect_trace_format(data)
    if fmt == "langfuse":
        return extract_tool_calls_langfuse(data, session)
    if fmt == "otlp":
        return extract_tool_calls_otlp(data, session)
    raise ValueError(f"unknown trace format: {fmt!r}")


def load_tool_calls(
    path: str | Path,
    session: str | None = None,
    *,
    fmt: str = "auto",
) -> list[ToolCall]:
    return extract_tool_calls(
        json.loads(Path(path).read_text(encoding="utf-8")),
        session,
        fmt=fmt,
    )
