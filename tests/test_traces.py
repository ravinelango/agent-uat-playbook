import json
from pathlib import Path

from agent_uat.traces import extract_tool_calls, load_tool_calls

FIXTURE = Path(__file__).parent.parent / "examples" / "traces" / "support_agent_otlp.json"


def test_otlp_fixture_orders_by_start_time_and_filters_session():
    calls = load_tool_calls(FIXTURE, session="run-1")
    assert [c.name for c in calls] == ["lookup_order", "create_refund_request"]
    assert calls[1].arguments == {"order_id": "A1001", "reason": "changed mind"}
    assert calls[0].call_id == "call_b7ad6b7169203332"


def test_without_session_returns_every_tool_span():
    assert len(load_tool_calls(FIXTURE)) == 3


def test_flat_span_list_and_non_tool_spans_ignored():
    data = {"spans": [
        {"startTimeUnixNano": 2, "attributes": {"gen_ai.operation.name": "chat"}},
        {"startTimeUnixNano": 1, "attributes": {"gen_ai.operation.name": "execute_tool",
                                                "gen_ai.tool.name": "get_tracking"}},
        {"startTimeUnixNano": 3, "attributes": {"gen_ai.operation.name": "execute_tool"}},
    ]}
    calls = extract_tool_calls(data)
    assert [c.name for c in calls] == ["get_tracking"] and calls[0].arguments == {}


def test_unparseable_arguments_are_kept_raw():
    data = [{"attributes": {"gen_ai.operation.name": "execute_tool", "gen_ai.tool.name": "t",
                            "gen_ai.tool.call.arguments": "not json"}}]
    assert extract_tool_calls(data)[0].arguments == {"_raw": "not json"}


def test_int_attribute_values_decode():
    data = {"resourceSpans": [{"scopeSpans": [{"spans": [{"attributes": [
        {"key": "gen_ai.operation.name", "value": {"stringValue": "execute_tool"}},
        {"key": "gen_ai.tool.name", "value": {"stringValue": "t"}},
        {"key": "session.id", "value": {"intValue": "7"}},
    ]}]}]}]}
    assert len(extract_tool_calls(json.loads(json.dumps(data)), session="7")) == 1


def test_cli_trace_prints_results_entry(capsys):
    from agent_uat.cli import main

    assert main(["trace", "--trace", str(FIXTURE), "--scenario-id", "REF-01",
                 "--session", "run-1"]) == 0
    entry = json.loads(capsys.readouterr().out)
    assert entry == {"scenario_id": "REF-01",
                     "actual_tool_calls": ["lookup_order", "create_refund_request"]}
