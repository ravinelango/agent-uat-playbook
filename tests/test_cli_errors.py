from pathlib import Path

import pytest

from agent_uat.cli import main

EX = Path(__file__).resolve().parents[1] / "examples"


@pytest.mark.parametrize(
    "argv",
    [
        ["validate", "--scenarios", "nope.json"],
        ["script", "--scenarios", "nope.json"],
        [
            "signoff",
            "--scenarios",
            str(EX / "support_agent_scenarios.json"),
            "--results",
            "nope.json",
        ],
        ["trace", "--trace", "nope.json", "--scenario-id", "X"],
    ],
)
def test_missing_input_file_exits_2(argv, tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    assert main(argv) == 2
    err = capsys.readouterr().err
    assert "no such file" in err
    assert "nope.json" in err
