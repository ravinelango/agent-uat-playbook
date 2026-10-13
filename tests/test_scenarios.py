import json

import pytest

from agent_uat.scenarios import load_scenarios, parse_scenario, to_test_script

BASE = {"id": "S1", "title": "t", "given": "g", "when": "w", "then": ["x"]}


def test_parse_defaults_and_lists():
    s = parse_scenario(BASE)
    assert s.priority == "medium" and s.given == ["g"] and s.guardrails == []


def test_rejects_missing_and_bad_priority():
    with pytest.raises(ValueError, match="when"):
        parse_scenario({**BASE, "when": ""})
    with pytest.raises(ValueError, match="priority"):
        parse_scenario({**BASE, "priority": "urgent"})


def test_rejects_expected_and_forbidden_overlap():
    with pytest.raises(ValueError, match="both"):
        parse_scenario({**BASE, "expected_tool_calls": ["a"], "forbidden_tool_calls": ["a"]})


def test_duplicate_ids(tmp_path):
    p = tmp_path / "s.json"
    p.write_text(json.dumps({"scenarios": [BASE, BASE]}))
    with pytest.raises(ValueError, match="duplicate"):
        load_scenarios(p)


def test_test_script_has_checkboxes():
    s = parse_scenario({**BASE, "forbidden_tool_calls": ["issue_refund"], "guardrails": ["g1"]})
    md = to_test_script([s])
    assert "- [ ] x" in md and "must NOT call" in md and "- [ ] g1" in md
