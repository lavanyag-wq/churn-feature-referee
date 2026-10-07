"""The offline (training) pipeline: batch-style computation over the Delta table.

Written the way feature-store batch jobs are written: load everything, group
by user, aggregate per feature. Correct behaviour reads the frozen snapshot
version of the table. The defects it can carry are the two that production
offline pipelines actually grow: leak_future (anchoring windows at the newest day in
an unfrozen table instead of at the label cutoff), tz_shift (interpreting
event days one day late, the integer-day stand-in for a UTC/local mixup),
and exclusive_window, which exists on both sides because in the wild it
arrives through a shared helper copy-pasted between the batch job and the
service: the shared-bug case the parity check cannot see.
"""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from .errors import UsageError
from .events import load_events, read_meta
from .spec import FeatureSpec

OFFLINE_DEFECTS = frozenset({"leak_future", "tz_shift", "exclusive_window"})


class OfflinePipeline:
    def __init__(self, defects: frozenset[str] | set[str] = frozenset()):
        unknown = set(defects) - OFFLINE_DEFECTS
        if unknown:
            raise UsageError(f"unknown offline defects: {sorted(unknown)}")
        self.defects = frozenset(defects)

    def compute(self, table_path: Path, specs: tuple[FeatureSpec, ...],
                cutoff_day: int) -> dict[tuple[str, str], float]:
        meta = read_meta(table_path)
        leaky = "leak_future" in self.defects
        version = None if leaky else meta["snapshot_version"]
        events = load_events(table_path, version=version)
        if "tz_shift" in self.defects:
            events = [type(e)(e.user_id, e.day + 1, e.etype, e.minutes) for e in events]
        # The leak is the classic "as of now" bug: the job reads the unfrozen
        # table and anchors every window at the newest day it can see, instead
        # of at the label cutoff the training set was built against.
        reference_day = max(e.day for e in events) if leaky else cutoff_day

        by_user: dict[str, list] = defaultdict(list)
        for e in events:
            by_user[e.user_id].append(e)
        users = sorted({e.user_id for e in load_events(table_path, version=None)})

        values: dict[tuple[str, str], float] = {}
        for user in users:
            rows = by_user.get(user, [])
            for spec in specs:
                values[(user, spec.name)] = self._one(rows, spec, reference_day)
        return values

    def _one(self, rows: list, spec: FeatureSpec, cutoff_day: int) -> float:
        relevant = [e for e in rows if e.etype == spec.source or spec.source == "any"]
        if spec.agg == "days_since_last":
            days = [e.day for e in relevant if e.day <= cutoff_day]
            return float(cutoff_day - max(days)) if days else spec.null_default
        start = spec.window_start(cutoff_day)
        if "exclusive_window" in self.defects:
            in_window = [e for e in relevant if start <= e.day < cutoff_day]
        else:
            in_window = [e for e in relevant if start <= e.day <= cutoff_day]
        if not in_window:
            return spec.null_default
        if spec.agg == "count":
            return float(len(in_window))
        if spec.agg == "sum":
            return float(sum(e.minutes for e in in_window))
        return float(len({e.day for e in in_window}))  # distinct_days
