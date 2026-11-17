from pathlib import Path

import pytest

from agent_uat import __version__
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


def test_version_flag_prints_package_version(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["--version"])
    assert exc.value.code == 0
    assert capsys.readouterr().out.strip() == f"agent-uat {__version__}"


@pytest.mark.parametrize("rate", ["90", "-0.1", "1.5"])
def test_signoff_min_pass_rate_out_of_range_exits_2(rate, tmp_path, capsys):
    argv = [
        "signoff",
        "--scenarios",
        str(EX / "support_agent_scenarios.json"),
        "--results",
        str(EX / "support_agent_results.json"),
        "--min-pass-rate",
        rate,
        "--out",
        str(tmp_path / "report.md"),
    ]
    assert main(argv) == 2
    assert "--min-pass-rate must be between 0 and 1" in capsys.readouterr().err
    assert not (tmp_path / "report.md").exists()


@pytest.mark.parametrize("rate", ["0", "1"])
def test_signoff_min_pass_rate_bounds_are_accepted(rate, tmp_path):
    argv = [
        "signoff",
        "--scenarios",
        str(EX / "support_agent_scenarios.json"),
        "--results",
        str(EX / "support_agent_results.json"),
        "--min-pass-rate",
        rate,
        "--out",
        str(tmp_path / "report.md"),
    ]
    assert main(argv) == 0
    assert (tmp_path / "report.md").is_file()
