"""Attribution classes, report shape, and the CLI exit code contract."""

import json

import pytest

from churn_feature_referee.cli import SCENARIOS, main
from churn_feature_referee.errors import (
    EXIT_CLEAN,
    EXIT_DEFECTS,
    EXIT_ERROR,
    EXIT_UNATTRIBUTED,
    UsageError,
)
from churn_feature_referee.referee import (
    AGREE_WRONG,
    CLEAN,
    DIVERGENT,
    OFFLINE_WRONG,
    SERVING_WRONG,
    AuditReport,
    Finding,
    attribute,
    classify,
)


@pytest.mark.parametrize("offline,serving,referee,expected", [
    (1.0, 1.0, 1.0, CLEAN),
    (1.0, 2.0, 1.0, SERVING_WRONG),
    (2.0, 1.0, 1.0, OFFLINE_WRONG),
    (2.0, 2.0, 1.0, AGREE_WRONG),
    (1.0, 2.0, 3.0, DIVERGENT),
])
def test_every_three_way_outcome_maps_to_exactly_one_class(offline, serving, referee, expected):
    assert classify(offline, serving, referee) == expected


def test_attribution_refuses_partial_overlap_between_the_three_computations():
    full = {("u1", "f"): 1.0, ("u2", "f"): 1.0}
    partial = {("u1", "f"): 1.0}
    with pytest.raises(UsageError, match="different .* pairs"):
        attribute(full, partial, full, cutoff_day=400)


def test_parity_mismatches_exclude_the_agree_wrong_class():
    report = AuditReport(cutoff_day=400, n_users=2, n_features=1, findings=[
        Finding("u1", "f", 2.0, 2.0, 1.0, AGREE_WRONG),
        Finding("u2", "f", 2.0, 1.0, 1.0, OFFLINE_WRONG),
    ])
    assert report.parity_mismatches == 1
    assert report.wrong_pairs == 2


def test_the_verdict_ladder_is_unattributed_over_defects_over_clean():
    base = dict(cutoff_day=400, n_users=1, n_features=1)
    clean = AuditReport(**base, findings=[Finding("u", "f", 1.0, 1.0, 1.0, CLEAN)])
    defects = AuditReport(**base, findings=[Finding("u", "f", 2.0, 1.0, 1.0, OFFLINE_WRONG)])
    unattributed = AuditReport(**base, findings=[Finding("u", "f", 1.0, 2.0, 3.0, DIVERGENT)])
    assert clean.verdict == "CLEAN"
    assert defects.verdict == "DEFECTS"
    assert unattributed.verdict == "UNATTRIBUTED"


def test_the_report_json_excludes_clean_findings_and_keeps_the_counts(tmp_path):
    report = AuditReport(cutoff_day=400, n_users=2, n_features=1, findings=[
        Finding("u1", "f", 1.0, 1.0, 1.0, CLEAN),
        Finding("u2", "f", 2.0, 2.0, 1.0, AGREE_WRONG),
    ])
    path = tmp_path / "r.json"
    report.save(path)
    raw = json.loads(path.read_text())
    assert raw["n_pairs"] == 2
    assert raw["counts"]["AGREE_WRONG"] == 1
    assert len(raw["findings"]) == 1
    assert raw["by_feature"] == {"f": {"AGREE_WRONG": 1}}


# CLI ---------------------------------------------------------------------

@pytest.fixture(scope="module")
def table(tmp_path_factory):
    path = tmp_path_factory.mktemp("cli") / "t"
    assert main(["generate", "--seed", "11", "--users", "40",
                 "--out", str(path)]) == EXIT_CLEAN
    return path


def test_generate_reports_the_two_commits(tmp_path, capsys):
    path = tmp_path / "t"
    assert main(["generate", "--seed", "11", "--users", "40", "--out", str(path)]) == 0
    out = capsys.readouterr().out
    assert "version 0" in out and "version 1" in out


def test_the_clean_scenario_exits_zero(table):
    assert main(["audit", "--table", str(table)]) == EXIT_CLEAN


@pytest.mark.parametrize("scenario", ["serving_window", "null_bug", "offline_leak",
                                      "offline_tz", "shared_window"])
def test_single_side_and_shared_defect_scenarios_exit_one(table, scenario):
    assert main(["audit", "--table", str(table), "--scenario", scenario]) == EXIT_DEFECTS


def test_the_messy_scenario_exits_two_because_divergent_pairs_exist(table, capsys):
    code = main(["audit", "--table", str(table), "--scenario", "messy"])
    assert code == EXIT_UNATTRIBUTED
    assert "divergent" in capsys.readouterr().out


def test_the_shared_bug_summary_shows_zero_parity_and_nonzero_wrong(table, capsys):
    main(["audit", "--table", str(table), "--scenario", "shared_window"])
    out = capsys.readouterr().out
    assert "parity check would report: 0 mismatches" in out
    assert "agree but wrong" in out


def test_an_unknown_scenario_exits_three_with_the_choices_listed(table, capsys):
    assert main(["audit", "--table", str(table), "--scenario", "ghost"]) == EXIT_ERROR
    assert "choose from" in capsys.readouterr().err


def test_auditing_a_missing_table_exits_three(tmp_path):
    assert main(["audit", "--table", str(tmp_path / "ghost")]) == EXIT_ERROR


def test_audit_writes_the_report_when_out_is_given(table, tmp_path):
    out = tmp_path / "report.json"
    main(["audit", "--table", str(table), "--scenario", "serving_window",
          "--out", str(out)])
    raw = json.loads(out.read_text())
    assert raw["verdict"] == "DEFECTS"
    assert raw["counts"]["SERVING_WRONG"] > 0


def test_every_scenario_name_uses_only_known_defects():
    from churn_feature_referee.offline import OFFLINE_DEFECTS
    from churn_feature_referee.serving import SERVING_DEFECTS
    for _name, (off, srv) in SCENARIOS.items():
        assert off <= OFFLINE_DEFECTS
        assert srv <= SERVING_DEFECTS
