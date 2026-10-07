"""Experiment: how big the point-in-time leak is, not only how many pairs it hits.

Question the README asks: the offline_leak scenario anchors windows at the
newest day in an unfrozen Delta table instead of at the label cutoff; how far
wrong do the feature values go? For every pair the leak corrupts, measure the
absolute error against the referee, then report the count, the mean absolute
error per corrupted pair and the worst single pair, per feature. Counts and
value units (events, minutes, days) only; nothing here depends on the machine.
Writes docs/experiments/leak_magnitude.json.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from churn_feature_referee.events import generate_events, load_events, read_meta, write_delta
from churn_feature_referee.offline import OfflinePipeline
from churn_feature_referee.referee import referee_compute
from churn_feature_referee.spec import SPECS

OUT = Path(__file__).resolve().parent.parent / "docs" / "experiments" / "leak_magnitude.json"


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        table = Path(tmp) / "t"
        events = generate_events(seed=11, n_users=120, cutoff_day=400)
        write_delta(events, table, cutoff_day=400)
        meta = read_meta(table)
        cutoff = meta["cutoff_day"]
        leaky = OfflinePipeline({"leak_future"}).compute(table, SPECS, cutoff)
        snapshot = load_events(table, version=meta["snapshot_version"])
        referee = referee_compute(snapshot, SPECS, cutoff)

    per_feature: dict[str, list[float]] = {s.name: [] for s in SPECS}
    for key, ref_val in referee.items():
        if leaky[key] != ref_val:
            per_feature[key[1]].append(abs(leaky[key] - ref_val))
    rows = []
    for spec in SPECS:
        errors = per_feature[spec.name]
        rows.append({
            "feature": spec.name,
            "corrupted_pairs": len(errors),
            "mean_abs_error": round(sum(errors) / len(errors), 2) if errors else 0.0,
            "worst_abs_error": max(errors) if errors else 0.0,
        })
    total = sum(r["corrupted_pairs"] for r in rows)
    payload = {"seed": 11, "n_users": 120, "total_corrupted_pairs": total, "rows": rows}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=1, sort_keys=True))
    print("the as-of-now leak, measured against the referee")
    print(f"{'feature':<24} {'pairs':>6} {'mean abs err':>13} {'worst':>7}")
    for r in rows:
        print(f"{r['feature']:<24} {r['corrupted_pairs']:>6} "
              f"{r['mean_abs_error']:>13.2f} {r['worst_abs_error']:>7.1f}")
    print(f"total corrupted pairs: {total}")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
