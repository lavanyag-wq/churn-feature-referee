"""The serving (online) pipeline: per-request computation over live state.

Written the way online feature services are written: one user at a time, from
an in-memory event state that only ever contains events at or before the
cutoff (the online store has no future). Its defects are the two that online
paths actually grow: exclusive_window (a strict less-than where the spec says
inclusive, so events on the cutoff day vanish from every windowed feature)
and null_default_zero (returning 0 for days_since_last_login when the user
never logged in, which tells the model the user logged in today).
"""

from __future__ import annotations

from collections import defaultdict

from .errors import UsageError
from .events import Event
from .spec import FeatureSpec

SERVING_DEFECTS = frozenset({"exclusive_window", "null_default_zero"})


class ServingPipeline:
    def __init__(self, defects: frozenset[str] | set[str] = frozenset()):
        unknown = set(defects) - SERVING_DEFECTS
        if unknown:
            raise UsageError(f"unknown serving defects: {sorted(unknown)}")
        self.defects = frozenset(defects)

    def compute(self, events: list[Event], specs: tuple[FeatureSpec, ...],
                cutoff_day: int) -> dict[tuple[str, str], float]:
        if any(e.day > cutoff_day for e in events):
            raise UsageError("serving state contains events after the cutoff; "
                             "the online store has no future, refuse rather than filter")
        state: dict[str, list[Event]] = defaultdict(list)
        for e in events:
            state[e.user_id].append(e)
        values: dict[tuple[str, str], float] = {}
        for user in sorted(state):
            for spec in specs:
                values[(user, spec.name)] = self._request(state[user], spec, cutoff_day)
        return values

    def _request(self, rows: list[Event], spec: FeatureSpec, cutoff_day: int) -> float:
        relevant = [e for e in rows if e.etype == spec.source or spec.source == "any"]
        if spec.agg == "days_since_last":
            days = [e.day for e in relevant]
            if not days:
                return 0.0 if "null_default_zero" in self.defects else spec.null_default
            return float(cutoff_day - max(days))
        start = spec.window_start(cutoff_day)
        end_ok = (lambda d: d < cutoff_day) if "exclusive_window" in self.defects \
            else (lambda d: d <= cutoff_day)
        in_window = [e for e in relevant if start <= e.day and end_ok(e.day)]
        if not in_window:
            return spec.null_default
        if spec.agg == "count":
            return float(len(in_window))
        if spec.agg == "sum":
            return float(sum(e.minutes for e in in_window))
        return float(len({e.day for e in in_window}))
