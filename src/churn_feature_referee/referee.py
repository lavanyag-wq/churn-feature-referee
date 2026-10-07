"""The referee: a third implementation compiled from the spec, and attribution.

The referee exists because a two-sided diff is symmetric. With three
implementations of the same declared semantics, every (user, feature)
mismatch falls into exactly one attribution class: SERVING_WRONG (offline
agrees with the referee), OFFLINE_WRONG (serving agrees with the referee),
AGREE_WRONG (offline and serving agree with each other and both differ from
the referee: the shared bug the parity check structurally cannot see), or
DIVERGENT (all three differ: something is wrong and no single side can be
named, which is its own verdict rather than a guess).

The referee's authority is not that it is code (code is what went wrong on
the other two sides); its authority is that it is the shortest possible
distance from the declared spec, written per-spec with no shared window
helper, and pinned by hand-computed test cases on the boundary days.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from .errors import UsageError
from .events import Event
from .spec import FeatureSpec

CLEAN = "CLEAN"
SERVING_WRONG = "SERVING_WRONG"
OFFLINE_WRONG = "OFFLINE_WRONG"
AGREE_WRONG = "AGREE_WRONG"
DIVERGENT = "DIVERGENT"

VERDICT_CLEAN = "CLEAN"
VERDICT_DEFECTS = "DEFECTS"
VERDICT_UNATTRIBUTED = "UNATTRIBUTED"


def referee_value(events: list[Event], spec: FeatureSpec, cutoff_day: int) -> float:
    """The spec, executed as directly as it reads."""
    rows = [e for e in events
            if (e.etype == spec.source or spec.source == "any") and e.day <= cutoff_day]
    if spec.agg == "days_since_last":
        return float(cutoff_day - max(e.day for e in rows)) if rows else spec.null_default
    rows = [e for e in rows if e.day >= spec.window_start(cutoff_day)]
    if not rows:
        return spec.null_default
    if spec.agg == "count":
        return float(len(rows))
    if spec.agg == "sum":
        return float(sum(e.minutes for e in rows))
    return float(len({e.day for e in rows}))


def referee_compute(events: list[Event], specs: tuple[FeatureSpec, ...],
                    cutoff_day: int) -> dict[tuple[str, str], float]:
    users = sorted({e.user_id for e in events})
    by_user: dict[str, list[Event]] = {u: [] for u in users}
    for e in events:
        by_user[e.user_id].append(e)
    return {(u, s.name): referee_value(by_user[u], s, cutoff_day)
            for u in users for s in specs}


@dataclass(frozen=True)
class Finding:
    user_id: str
    feature: str
    offline: float
    serving: float
    referee: float
    klass: str


@dataclass
class AuditReport:
    cutoff_day: int
    n_users: int
    n_features: int
    findings: list[Finding] = field(default_factory=list)

    @property
    def n_pairs(self) -> int:
        return self.n_users * self.n_features

    def count(self, klass: str) -> int:
        return sum(1 for f in self.findings if f.klass == klass)

    @property
    def parity_mismatches(self) -> int:
        """What a plain two-sided parity check would report."""
        return sum(1 for f in self.findings
                   if f.klass in (SERVING_WRONG, OFFLINE_WRONG, DIVERGENT))

    @property
    def wrong_pairs(self) -> int:
        return sum(1 for f in self.findings if f.klass != CLEAN)

    @property
    def verdict(self) -> str:
        if self.count(DIVERGENT):
            return VERDICT_UNATTRIBUTED
        if self.wrong_pairs:
            return VERDICT_DEFECTS
        return VERDICT_CLEAN

    def by_feature(self) -> dict[str, dict[str, int]]:
        out: dict[str, dict[str, int]] = {}
        for f in self.findings:
            if f.klass == CLEAN:
                continue
            out.setdefault(f.feature, {}).setdefault(f.klass, 0)
            out[f.feature][f.klass] += 1
        return out

    def to_json(self) -> dict:
        return {
            "cutoff_day": self.cutoff_day,
            "n_users": self.n_users,
            "n_features": self.n_features,
            "n_pairs": self.n_pairs,
            "verdict": self.verdict,
            "parity_mismatches": self.parity_mismatches,
            "wrong_pairs": self.wrong_pairs,
            "counts": {k: self.count(k) for k in
                       (SERVING_WRONG, OFFLINE_WRONG, AGREE_WRONG, DIVERGENT)},
            "by_feature": self.by_feature(),
            "findings": [vars(f) for f in self.findings if f.klass != CLEAN],
        }

    def save(self, path: Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_json(), indent=1, sort_keys=True))


def classify(offline: float, serving: float, referee: float) -> str:
    if offline == serving == referee:
        return CLEAN
    if offline == serving:
        return AGREE_WRONG
    if offline == referee:
        return SERVING_WRONG
    if serving == referee:
        return OFFLINE_WRONG
    return DIVERGENT


def attribute(offline_vals: dict, serving_vals: dict, referee_vals: dict,
              cutoff_day: int) -> AuditReport:
    if set(offline_vals) != set(referee_vals) or set(serving_vals) != set(referee_vals):
        raise UsageError("the three computations cover different (user, feature) pairs; "
                         "attribution over a partial overlap would be misleading")
    users = {u for (u, _f) in referee_vals}
    features = {f for (_u, f) in referee_vals}
    report = AuditReport(cutoff_day=cutoff_day, n_users=len(users), n_features=len(features))
    for key in sorted(referee_vals):
        user, feat = key
        klass = classify(offline_vals[key], serving_vals[key], referee_vals[key])
        report.findings.append(Finding(user, feat, offline_vals[key],
                                       serving_vals[key], referee_vals[key], klass))
    return report
