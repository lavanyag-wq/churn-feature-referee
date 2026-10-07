"""Experiment: the parity check's blind spot, measured.

Question the README asks: when the batch job and the service share the same
window helper and therefore the same bug, what does each instrument see? The
shared_window scenario plants the identical strict less-than on both sides.
Parity compares offline to serving and sees agreement everywhere; the referee
compares both to the spec. The second table asks how the blind spot scales
with how active the cutoff day is, by sweeping the seed: the bug only shows
on users with cutoff-day events, so the wrong-pair count is corpus-dependent
and the share is the honest unit. Writes docs/experiments/blindspot.json.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from churn_feature_referee.events import generate_events, load_events, read_meta, write_delta
from churn_feature_referee.offline import OfflinePipeline
from churn_feature_referee.referee import attribute, referee_compute
from churn_feature_referee.serving import ServingPipeline
from churn_feature_referee.spec import SPECS

OUT = Path(__file__).resolve().parent.parent / "docs" / "experiments" / "blindspot.json"
SEEDS = [11, 12, 13, 14, 15]


def shared_bug_audit(seed: int) -> dict:
    with tempfile.TemporaryDirectory() as tmp:
        table = Path(tmp) / "t"
        events = generate_events(seed=seed, n_users=120, cutoff_day=400)
        write_delta(events, table, cutoff_day=400)
        meta = read_meta(table)
        cutoff = meta["cutoff_day"]
        offline_vals = OfflinePipeline({"exclusive_window"}).compute(table, SPECS, cutoff)
        snapshot = load_events(table, version=0)
        serving_vals = ServingPipeline({"exclusive_window"}).compute(snapshot, SPECS, cutoff)
        referee_vals = referee_compute(snapshot, SPECS, cutoff)
        report = attribute(offline_vals, serving_vals, referee_vals, cutoff)
        affected_users = {f.user_id for f in report.findings if f.klass != "CLEAN"}
        return {
            "seed": seed,
            "n_pairs": report.n_pairs,
            "parity_mismatches": report.parity_mismatches,
            "agree_wrong": report.count("AGREE_WRONG"),
            "wrong_share_pct": round(100 * report.wrong_pairs / report.n_pairs, 1),
            "affected_users": len(affected_users),
        }


def main() -> None:
    rows = [shared_bug_audit(seed) for seed in SEEDS]
    headline = rows[0]
    payload = {"scenario": "shared exclusive_window on both sides",
               "headline_seed": SEEDS[0], "rows": rows}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=1, sort_keys=True))
    print("same bug on both sides: what each instrument reports")
    print(f"{'seed':>5} {'pairs':>6} {'parity sees':>12} {'referee sees':>13} "
          f"{'share':>7} {'users hit':>10}")
    for r in rows:
        print(f"{r['seed']:>5} {r['n_pairs']:>6} {r['parity_mismatches']:>12} "
              f"{r['agree_wrong']:>13} {r['wrong_share_pct']:>6.1f}% {r['affected_users']:>10}")
    print(f"\nheadline (seed {headline['seed']}): parity {headline['parity_mismatches']}, "
          f"referee {headline['agree_wrong']} wrong pairs across "
          f"{headline['affected_users']} users")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
