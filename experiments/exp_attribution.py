"""Experiment: what the referee attributes under each single-defect scenario.

Question the README asks: when offline and serving disagree, can anything say
whose bug it is? For each scenario, run all three implementations over the
same seeded table and tabulate what a two-sided parity check would report
next to what the referee attributes. Writes docs/experiments/attribution.json.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from churn_feature_referee.cli import SCENARIOS
from churn_feature_referee.events import generate_events, load_events, read_meta, write_delta
from churn_feature_referee.offline import OfflinePipeline
from churn_feature_referee.referee import attribute, referee_compute
from churn_feature_referee.serving import ServingPipeline
from churn_feature_referee.spec import SPECS

OUT = Path(__file__).resolve().parent.parent / "docs" / "experiments" / "attribution.json"
ORDER = ["clean", "serving_window", "null_bug", "offline_leak", "offline_tz",
         "shared_window", "messy"]


def run_scenario(table: Path, name: str) -> dict:
    offline_defects, serving_defects = SCENARIOS[name]
    meta = read_meta(table)
    cutoff = meta["cutoff_day"]
    offline_vals = OfflinePipeline(offline_defects).compute(table, SPECS, cutoff)
    snapshot = load_events(table, version=meta["snapshot_version"])
    serving_vals = ServingPipeline(serving_defects).compute(snapshot, SPECS, cutoff)
    referee_vals = referee_compute(snapshot, SPECS, cutoff)
    report = attribute(offline_vals, serving_vals, referee_vals, cutoff)
    return {
        "scenario": name,
        "n_pairs": report.n_pairs,
        "parity_mismatches": report.parity_mismatches,
        "wrong_pairs": report.wrong_pairs,
        "serving_wrong": report.count("SERVING_WRONG"),
        "offline_wrong": report.count("OFFLINE_WRONG"),
        "agree_wrong": report.count("AGREE_WRONG"),
        "divergent": report.count("DIVERGENT"),
        "verdict": report.verdict,
    }


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        table = Path(tmp) / "t"
        events = generate_events(seed=11, n_users=120, cutoff_day=400)
        write_delta(events, table, cutoff_day=400)
        rows = [run_scenario(table, name) for name in ORDER]
    payload = {"seed": 11, "n_users": 120, "cutoff_day": 400, "rows": rows}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=1, sort_keys=True))
    header = (f"{'scenario':<15} {'parity':>7} {'wrong':>6} {'srv':>5} {'off':>5} "
              f"{'agree':>6} {'div':>4}  verdict")
    print(header)
    print("-" * len(header))
    for r in rows:
        print(f"{r['scenario']:<15} {r['parity_mismatches']:>7} {r['wrong_pairs']:>6} "
              f"{r['serving_wrong']:>5} {r['offline_wrong']:>5} {r['agree_wrong']:>6} "
              f"{r['divergent']:>4}  {r['verdict']}")
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
