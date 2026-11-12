import json

import pytest

from agent_uat.cli import main
from agent_uat.compare import compare, load_report, render_markdown


def _report(decision, statuses):
    return {
        "decision": decision,
        "pass_rate": None,
        "scenarios": [
            {"id": sid, "title": f"t-{sid}", "priority": "high", "status": st}
            for sid, st in statuses.items()
        ],
    }


def test_classifies_regression_fixed_added_removed():
    before = _report("GO", {"A": "pass", "B": "fail", "C": "pass", "D": "pass"})
    after = _report("NO-GO", {"A": "fail", "B": "pass", "C": "pass", "E": "pass"})
    c = compare(before, after)
    kinds = {x.id: x.kind for x in c.changes}
    assert kinds == {
        "A": "regression",
        "B": "fixed",
        "C": "unchanged",
        "D": "removed",
        "E": "added",
    }
    assert c.has_regression


def test_not_run_is_changed_not_regression():
    c = compare(_report("GO", {"A": "pass"}), _report("GO", {"A": "not run"}))
    assert c.changes[0].kind == "changed"
    assert not c.has_regression


def test_markdown_lists_regressions_first_and_skips_unchanged():
    before = _report("GO", {"A": "fail", "B": "pass", "C": "pass"})
    after = _report("NO-GO", {"A": "pass", "B": "blocked", "C": "pass"})
    md = render_markdown(compare(before, after), "b.json", "a.json")
    rows = [line for line in md.splitlines() if line.startswith("| ") and "Scenario" not in line]
    assert rows[0].startswith("| B ") and rows[0].endswith("| regression |")
    assert rows[1].startswith("| A ")
    assert "| C " not in md


def test_load_report_rejects_non_report(tmp_path):
    p = tmp_path / "x.json"
    p.write_text(json.dumps({"decision": "GO"}))
    with pytest.raises(ValueError):
        load_report(p)


def test_cli_compare_strict_exit_codes(tmp_path, capsys):
    b, a = tmp_path / "b.json", tmp_path / "a.json"
    b.write_text(json.dumps(_report("GO", {"A": "pass"})))
    a.write_text(json.dumps(_report("NO-GO", {"A": "fail"})))
    assert main(["compare", "--before", str(b), "--after", str(a)]) == 0
    assert main(["compare", "--before", str(b), "--after", str(a), "--strict"]) == 1
    assert main(["compare", "--before", str(b), "--after", str(b), "--strict"]) == 0
    assert "regression" in capsys.readouterr().out


def test_cli_compare_missing_file(tmp_path):
    assert (
        main(
            [
                "compare",
                "--before",
                str(tmp_path / "nope.json"),
                "--after",
                str(tmp_path / "nope.json"),
            ]
        )
        == 2
    )


def test_cli_compare_json_format(tmp_path, capsys):
    b, a = tmp_path / "b.json", tmp_path / "a.json"
    b.write_text(json.dumps(_report("GO", {"A": "pass", "B": "pass"})))
    a.write_text(json.dumps(_report("NO-GO", {"A": "fail", "B": "pass"})))
    assert main(["compare", "--before", str(b), "--after", str(a), "--format", "json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["has_regression"] is True
    assert data["counts"]["regression"] == 1 and data["counts"]["unchanged"] == 1
    assert [x["id"] for x in data["changes"]] == ["A"]
    assert data["after"]["decision"] == "NO-GO"


def test_cli_compare_json_inferred_from_out_suffix(tmp_path):
    b = tmp_path / "b.json"
    b.write_text(json.dumps(_report("GO", {"A": "pass"})))
    out = tmp_path / "cmp.json"
    assert main(["compare", "--before", str(b), "--after", str(b), "--out", str(out)]) == 0
    data = json.loads(out.read_text())
    assert data["has_regression"] is False and data["changes"] == []
