import json
from pathlib import Path

from agent_uat.cli import main
from agent_uat.scenarios import load_scenarios, parse_scenario
from agent_uat.signoff import evaluate

EX = Path(__file__).parents[1] / "examples"


def sc(i, priority="medium", **kw):
    return parse_scenario({"id": i, "title": i, "given": "g", "when": "w", "then": "t",
                           "priority": priority, **kw})


def res(i, status="pass", **kw):
    return {"scenario_id": i, "status": status, **kw}


def test_all_pass_is_go():
    ev = evaluate([sc("A", "critical"), sc("B")], {"results": [res("A"), res("B")]})
    assert ev.decision == "GO" and ev.pass_rate == 1.0


def test_failed_critical_is_no_go():
    ev = evaluate([sc("A", "critical")], {"results": [res("A", "fail")]}, min_pass_rate=0)
    assert ev.decision == "NO-GO" and "Critical scenario A" in ev.reasons[0]


def test_forbidden_tool_call_is_no_go_even_if_marked_pass():
    s = sc("A", forbidden_tool_calls=["issue_refund"])
    ev = evaluate([s], {"results": [res("A", actual_tool_calls=["issue_refund"])]})
    assert ev.decision == "NO-GO"


def test_open_s2_blocks_but_closed_does_not():
    data = {"results": [res("A")], "defects": [{"id": "D1", "severity": "S2"}]}
    assert evaluate([sc("A")], data).decision == "NO-GO"
    data["defects"][0]["status"] = "closed"
    assert evaluate([sc("A")], data).decision == "GO"


def test_conditions_for_s3_missing_tool_and_not_run():
    scen = [sc("A", expected_tool_calls=["t"]), *[sc(f"P{i}") for i in range(10)], sc("Z")]
    results = [res("A")] + [res(f"P{i}") for i in range(10)]
    data = {"results": results, "defects": [{"id": "D", "severity": "S3"}]}
    ev = evaluate(scen, data, min_pass_rate=0.8)
    assert ev.decision == "GO WITH CONDITIONS"
    assert len(ev.conditions) == 3


def test_pass_rate_threshold():
    ev = evaluate([sc("A"), sc("B")], {"results": [res("A"), res("B", "fail")]})
    assert ev.decision == "NO-GO" and "threshold" in ev.reasons[-1]


def test_example_end_to_end(tmp_path):
    out = tmp_path / "signoff.md"
    rc = main(["signoff", "--scenarios", str(EX / "support_agent_scenarios.json"),
               "--results", str(EX / "support_agent_results.json"), "--out", str(out)])
    assert rc == 0
    md = out.read_text()
    assert "NO-GO" in md and "SYNTHETIC" in md and "D-101" in md and "ERR-01" in md
    assert main(["signoff", "--scenarios", str(EX / "support_agent_scenarios.json"),
                 "--results", str(EX / "support_agent_results.json"), "--strict",
                 "--out", str(out)]) == 1


def test_example_scenarios_valid_and_script(tmp_path):
    assert len(load_scenarios(EX / "support_agent_scenarios.json")) == 6
    out = tmp_path / "script.md"
    assert main(["script", "--scenarios", str(EX / "support_agent_scenarios.json"),
                 "--out", str(out)]) == 0
    assert "REF-01" in out.read_text()
    json.loads((EX / "support_agent_results.json").read_text())
