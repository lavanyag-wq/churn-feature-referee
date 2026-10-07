"""Seeded event generator and the Delta table that is the offline source of truth.

The generator plants the hard cases on purpose: users whose only login sits
exactly on the cutoff day (invisible to an exclusive window), users whose
events sit exactly on a window's first day (off-by-one bait), users who never
log in (null-default bait), and late-arriving events dated after the cutoff
(point-in-time bait). Day numbers are integers (days since an arbitrary
epoch) so that no implementation can smuggle in a timezone library and every
boundary is exact arithmetic.

The Delta table is written in two commits. Version 0 contains exactly the
events dated at or before the cutoff: the training snapshot. Version 1
appends the late-arriving events. A correct offline pipeline reads version 0
(time travel); the leak_future defect reads the latest version, which is the
classic leakage bug of reading an unfrozen table.
"""

from __future__ import annotations

import json
import random
from dataclasses import dataclass
from pathlib import Path

import pyarrow as pa
from deltalake import DeltaTable, write_deltalake

from .errors import DataError, UsageError

EVENT_TYPES = ("login", "watch", "ticket")


@dataclass(frozen=True)
class Event:
    user_id: str
    day: int
    etype: str
    minutes: float  # 0.0 for non-watch events


def generate_events(seed: int, n_users: int = 120, cutoff_day: int = 400,
                    history_days: int = 120, future_days: int = 5) -> list[Event]:
    """Generate the event log, fully determined by the seed.

    Hard-case users (ids are stable so tests can point at them):
    u0000 never logs in; u0001's only login is exactly on the cutoff day;
    u0002 has one login exactly on the 30-day window's first day
    (cutoff - 29) and one the day before it (cutoff - 30, outside);
    u0003 has a late-arriving login after the cutoff and none before.
    """
    if n_users < 10:
        raise UsageError(f"n_users must be >= 10 to hold the hard cases, got {n_users}")
    if history_days < 91 or future_days < 1:
        raise UsageError("history_days must cover the 90-day window and future_days >= 1")
    rng = random.Random(seed)
    events: list[Event] = []

    def add(user, day, etype, minutes=0.0):
        events.append(Event(user, day, etype, float(minutes)))

    first_day = cutoff_day - history_days + 1
    for i in range(n_users):
        user = f"u{i:04d}"
        if i == 0:
            add(user, cutoff_day - 3, "watch", rng.randint(10, 60))
            continue  # never logs in
        if i == 1:
            add(user, cutoff_day, "login")
            add(user, cutoff_day, "watch", 25)
            continue
        if i == 2:
            add(user, cutoff_day - 29, "login")  # first day inside logins_30d
            add(user, cutoff_day - 30, "login")  # last day outside it
            continue
        if i == 3:
            add(user, cutoff_day + 2, "login")  # late-arriving only
            add(user, cutoff_day - 50, "ticket")
            continue
        n_events = rng.randint(3, 25)
        for _ in range(n_events):
            day = rng.randint(first_day, cutoff_day)
            etype = rng.choice(EVENT_TYPES)
            add(user, day, etype, rng.randint(5, 180) if etype == "watch" else 0.0)
        if rng.random() < 0.25:
            late_type = rng.choice(EVENT_TYPES)
            add(user, rng.randint(cutoff_day + 1, cutoff_day + future_days),
                late_type, rng.randint(5, 180) if late_type == "watch" else 0.0)
    events.sort(key=lambda e: (e.user_id, e.day, e.etype, e.minutes))
    return events


def _to_table(events: list[Event]) -> pa.Table:
    return pa.table({
        "user_id": [e.user_id for e in events],
        "day": pa.array([e.day for e in events], type=pa.int64()),
        "etype": [e.etype for e in events],
        "minutes": pa.array([e.minutes for e in events], type=pa.float64()),
    })


def write_delta(events: list[Event], path: Path, cutoff_day: int) -> dict:
    """Write the two-commit Delta table and a sidecar meta file. Returns meta."""
    snapshot = [e for e in events if e.day <= cutoff_day]
    late = [e for e in events if e.day > cutoff_day]
    if not snapshot:
        raise UsageError("no events at or before the cutoff; nothing to snapshot")
    path = Path(path)
    if path.exists() and any(path.iterdir()):
        raise UsageError(f"refusing to write over a non-empty directory: {path}")
    write_deltalake(str(path), _to_table(snapshot))
    if late:
        write_deltalake(str(path), _to_table(late), mode="append")
    meta = {
        "cutoff_day": cutoff_day,
        "snapshot_version": 0,
        "n_snapshot_events": len(snapshot),
        "n_late_events": len(late),
        "n_users": len({e.user_id for e in events}),
    }
    (path / "_referee_meta.json").write_text(json.dumps(meta, indent=1, sort_keys=True))
    return meta


def read_meta(path: Path) -> dict:
    meta_path = Path(path) / "_referee_meta.json"
    try:
        return json.loads(meta_path.read_text())
    except FileNotFoundError as exc:
        raise DataError(f"not a referee table (missing _referee_meta.json): {path}") from exc
    except json.JSONDecodeError as exc:
        raise DataError(f"corrupt meta file: {meta_path}") from exc


def load_events(path: Path, version: int | None = None) -> list[Event]:
    """Load events from the Delta table, optionally time-travelling to a version."""
    try:
        table = DeltaTable(str(path)) if version is None else DeltaTable(str(path), version=version)
    except Exception as exc:
        raise DataError(f"cannot open Delta table at {path}: {exc}") from exc
    data = table.to_pyarrow_table().to_pydict()
    events = [
        Event(u, int(d), t, float(m))
        for u, d, t, m in zip(data["user_id"], data["day"], data["etype"], data["minutes"],
                              strict=True)
    ]
    events.sort(key=lambda e: (e.user_id, e.day, e.etype, e.minutes))
    return events
