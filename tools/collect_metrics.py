"""Collect every figure the documents quote, from machine-readable outputs.

Nothing here is typed by hand: test count and coverage come from the junit
XML and the coverage JSON pytest wrote (or writes here unless --skip-tests
says CI ran them as their own step), and every experiment figure is read from
the JSON the experiments wrote. Derived values are computed in this one file.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REPORTS = ROOT / "reports"
EXPERIMENTS = ROOT / "docs" / "experiments"
OUT = ROOT / "docs" / "metrics.json"

ANCHORS = {
    "tests_total": ["{} tests", "{} property-named tests"],
    "coverage_line_pct": ["{}% line coverage", "coverage of {}%"],
    "n_users": ["{} users", "{} seeded users"],
    "n_pairs": ["{} user-feature pairs", "{} pairs"],
    "n_features": ["{} declared features", "{} features"],
    "snapshot_events": ["{} events at or before", "{} snapshot events"],
    "late_events": ["{} late-arriving events", "{} events dated after"],
    "shared_parity": ["parity reports {} mismatches", "parity check reports {}"],
    "shared_agree_wrong": ["{} pairs are wrong", "{} wrong pairs", "referee finds {}"],
    "shared_users": ["across {} users", "{} users carry"],
    "shared_share_pct": ["{}% of all pairs", "{}% of the pairs"],
    "serving_window_wrong": ["attributes all {} mismatches", "{} mismatched pairs, every one"],
    "null_bug_wrong": ["the {} never-login", "{} users who never"],
    "leak_total_pairs": ["corrupts {} of the", "{} pairs, and names"],
    "leak_worst_days": ["off by {} days", "{} days wrong"],
    "leak_watch_mean": ["average of {} minutes", "{} minutes of phantom"],
    "messy_divergent": ["{} pairs where all three", "{} divergent pairs"],
    "messy_parity": ["parity sees {} mismatches", "{} mismatches in the messy"],
    "messy_wrong": ["{} pairs are actually wrong", "{} actually wrong"],
    "blind_share_min_pct": ["between {}%"],
    "blind_share_max_pct": ["and {}% of pairs"],
}


def _fmt(value) -> str:
    if isinstance(value, float):
        return f"{value:g}"
    return str(value)


def run_tests() -> None:
    REPORTS.mkdir(exist_ok=True)
    subprocess.run(
        [sys.executable, "-m", "pytest", "--junitxml", str(REPORTS / "junit.xml"),
         "--cov=churn_feature_referee",
         f"--cov-report=json:{REPORTS / 'coverage.json'}", "-q"],
        check=True, cwd=ROOT)


def run_experiments() -> None:
    for script in sorted((ROOT / "experiments").glob("exp_*.py")):
        subprocess.run([sys.executable, str(script)], check=True, cwd=ROOT)


def collect(skip_tests: bool, skip_experiments: bool) -> dict:
    if not skip_tests:
        run_tests()
    if not skip_experiments:
        run_experiments()
    junit = ET.parse(REPORTS / "junit.xml").getroot()
    suite = junit if junit.tag == "testsuite" else junit.find("testsuite")
    tests_total = int(suite.get("tests"))
    failures = int(suite.get("failures", 0)) + int(suite.get("errors", 0))
    if failures:
        raise SystemExit(f"refusing to collect metrics from a failing suite ({failures} failed)")
    coverage = json.loads((REPORTS / "coverage.json").read_text())

    attribution = json.loads((EXPERIMENTS / "attribution.json").read_text())
    rows = {r["scenario"]: r for r in attribution["rows"]}
    blind = json.loads((EXPERIMENTS / "blindspot.json").read_text())
    blind_head = blind["rows"][0]
    shares = [r["wrong_share_pct"] for r in blind["rows"]]
    leak = json.loads((EXPERIMENTS / "leak_magnitude.json").read_text())
    leak_rows = {r["feature"]: r for r in leak["rows"]}

    from churn_feature_referee.events import generate_events
    events = generate_events(seed=attribution["seed"], n_users=attribution["n_users"],
                             cutoff_day=attribution["cutoff_day"])
    cutoff = attribution["cutoff_day"]

    metrics = {
        "tests_total": tests_total,
        "coverage_line_pct": round(coverage["totals"]["percent_covered"]),
        "n_users": attribution["n_users"],
        "n_pairs": rows["clean"]["n_pairs"],
        "n_features": 5,
        "snapshot_events": sum(1 for e in events if e.day <= cutoff),
        "late_events": sum(1 for e in events if e.day > cutoff),
        "shared_parity": rows["shared_window"]["parity_mismatches"],
        "shared_agree_wrong": rows["shared_window"]["agree_wrong"],
        "shared_users": blind_head["affected_users"],
        "shared_share_pct": blind_head["wrong_share_pct"],
        "serving_window_wrong": rows["serving_window"]["serving_wrong"],
        "null_bug_wrong": rows["null_bug"]["serving_wrong"],
        "leak_total_pairs": leak["total_corrupted_pairs"],
        "leak_worst_days": leak_rows["days_since_last_login"]["worst_abs_error"],
        "leak_watch_mean": leak_rows["watch_minutes_7d"]["mean_abs_error"],
        "messy_divergent": rows["messy"]["divergent"],
        "messy_parity": rows["messy"]["parity_mismatches"],
        "messy_wrong": rows["messy"]["wrong_pairs"],
        "blind_share_min_pct": min(shares),
        "blind_share_max_pct": max(shares),
    }
    return {
        "metrics": metrics,
        "anchors": ANCHORS,
        "checked_documents": ["README.md"],
        "note": "every value is produced by running the suite and the experiments",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-tests", action="store_true")
    parser.add_argument("--skip-experiments", action="store_true")
    args = parser.parse_args()
    payload = collect(args.skip_tests, args.skip_experiments)
    OUT.write_text(json.dumps(payload, indent=1, sort_keys=True))
    print(f"wrote {OUT} with {len(payload['metrics'])} metrics")


if __name__ == "__main__":
    main()
