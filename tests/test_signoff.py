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


def test_in_order_allows_calls_in_between():
    from agent_uat.signoff import in_order
    assert in_order(["a", "b"], ["a", "x", "b"])
    assert not in_order(["a", "b"], ["b", "a"])
    assert not in_order(["a", "a"], ["a"])


def test_out_of_order_blocks_critical_and_conditions_others():
    kw = {"expected_tool_calls": ["lookup_order", "create_refund_request"],
          "ordered_tool_calls": True}
    swapped = res("A", actual_tool_calls=["create_refund_request", "lookup_order"])
    ev = evaluate([sc("A", "critical", **kw)], {"results": [swapped]})
    assert ev.decision == "NO-GO" and "out of order" in ev.reasons[0]
    ev = evaluate([sc("A", **kw)], {"results": [swapped]})
    assert ev.decision == "GO WITH CONDITIONS" and "out of order" in ev.conditions[0]
    ok = res("A", actual_tool_calls=["lookup_order", "get_tracking", "create_refund_request"])
    assert evaluate([sc("A", "critical", **kw)], {"results": [ok]}).decision == "GO"


def test_argument_checks_use_tool_call_details():
    s = sc("A", "critical", expected_tool_calls=["lookup_order"],
           tool_argument_checks=[{"tool": "lookup_order", "args": {"order_id": "A1001"}}])
    good = res("A", actual_tool_calls=["lookup_order"],
               tool_call_details=[{"name": "lookup_order", "arguments": {"order_id": "A1001",
                                                                         "fields": "all"}}])
    assert evaluate([s], {"results": [good]}).decision == "GO"
    bad = res("A", actual_tool_calls=["lookup_order"],
              tool_call_details=[{"name": "lookup_order", "arguments": {"order_id": "A1002"}}])
    ev = evaluate([s], {"results": [bad]})
    assert ev.decision == "NO-GO" and "order_id='A1001'" in ev.reasons[0]


def test_argument_checks_without_details_are_a_condition():
    s = sc("A", expected_tool_calls=["lookup_order"],
           tool_argument_checks=[{"tool": "lookup_order", "args": {"order_id": "A1001"}}])
    ev = evaluate([s], {"results": [res("A", actual_tool_calls=["lookup_order"])]})
    assert ev.decision == "GO WITH CONDITIONS" and "not verified" in ev.conditions[0]


def test_run_stats_from_outcomes_and_totals():
    from agent_uat.signoff import run_stats
    st = run_stats(res("A", "fail", run_outcomes=["pass", "pass", "fail"]))
    assert st.runs == 3 and st.passed == 2 and st.failed == 1 and st.blocked == 0
    assert st.pass_rate == 2 / 3 and st.unstable
    st = run_stats(res("B", runs_passed=3, runs_total=3))
    assert st.summary() == "3/3" and not st.unstable and st.pass_rate == 1.0
    st = run_stats(res("C", "blocked", runs_passed=0, runs_total=2))
    assert st.blocked == 2 and st.failed == 0 and not st.unstable
    st = run_stats(res("D", "fail", runs_passed=1, runs_total=3, runs_blocked=1))
    assert st.passed == 1 and st.failed == 1 and st.blocked == 1 and st.unstable


def test_unstable_multi_run_is_a_condition():
    data = {"results": [res("A", "fail", run_outcomes=["pass", "fail", "pass"])]}
    ev = evaluate([sc("A")], data, min_pass_rate=0)
    assert ev.decision == "GO WITH CONDITIONS"
    assert any("unstable" in c and "2 pass" in c and "1 fail" in c for c in ev.conditions)
    assert ev.rows[0]["stats"].unstable


def test_multi_run_section_in_example_report(tmp_path):
    out = tmp_path / "signoff.md"
    assert main(["signoff", "--scenarios", str(EX / "support_agent_scenarios.json"),
                 "--results", str(EX / "support_agent_results.json"), "--out", str(out)]) == 0
    md = out.read_text()
    assert "## Multi-run statistics" in md
    assert "| INJ-01 | 3 | 2 | 1 | 0 | 67% | no |" in md
    assert "unstable across runs" in md


def test_html_signoff_report(tmp_path):
    out = tmp_path / "signoff.html"
    rc = main(["signoff", "--scenarios", str(EX / "support_agent_scenarios.json"),
               "--results", str(EX / "support_agent_results.json"), "--out", str(out)])
    assert rc == 0
    doc = out.read_text()
    assert doc.startswith("<!doctype html>")
    assert "NO-GO" in doc and "SYNTHETIC" in doc and "D-101" in doc and "INJ-01" in doc
    assert "Multi-run statistics" in doc
    assert "print-color-adjust" in doc or "@media print" in doc


def test_format_flag_forces_html_without_html_suffix(tmp_path):
    out = tmp_path / "signoff.txt"
    assert main(["signoff", "--scenarios", str(EX / "support_agent_scenarios.json"),
                 "--results", str(EX / "support_agent_results.json"),
                 "--format", "html", "--out", str(out)]) == 0
    assert out.read_text().startswith("<!doctype html>")


def test_rcm_prior_auth_example_end_to_end(tmp_path):
    """Synthetic RCM prior-auth set loads and signs off as NO-GO."""
    scen = EX / "rcm_prior_auth_scenarios.json"
    res_path = EX / "rcm_prior_auth_results.json"
    assert len(load_scenarios(scen)) == 5
    out = tmp_path / "rcm_signoff.md"
    rc = main(["signoff", "--scenarios", str(scen), "--results", str(res_path), "--out", str(out)])
    assert rc == 0
    md = out.read_text()
    assert "NO-GO" in md and "SYNTHETIC" in md
    assert "D-PA-101" in md and "PA-CIT-01" in md and "PA-DENY-01" in md
    assert "L99999" in md or "invented" in md.lower() or "guardrail" in md.lower()
    assert main(["signoff", "--scenarios", str(scen), "--results", str(res_path),
                 "--strict", "--out", str(out)]) == 1
    assert main(["validate", "--scenarios", str(scen)]) == 0
    json.loads(res_path.read_text())


def test_rcm_defect_triage_walkthrough_doc():
    """Docs walkthrough must cover the three open S1s from the synthetic NO-GO sign-off."""
    doc = Path(__file__).parents[1] / "docs" / "rcm-defect-triage-walkthrough.md"
    text = doc.read_text(encoding="utf-8")
    for token in ("D-PA-101", "D-PA-102", "D-PA-103", "NO-GO", "S1", "AUTH_MISSING"):
        assert token in text, token
