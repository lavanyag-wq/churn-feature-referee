"""The feature spec: the single declared semantics all three implementations serve.

Every ambiguity that produces training/serving skew in the wild is pinned here
as an explicit rule, so that "correct" has a referent. The rules: a window of
W days ending at the cutoff covers days [cutoff - W + 1, cutoff], both ends
inclusive; events after the cutoff never count toward any feature
(point-in-time rule); a feature whose source events are absent for a user
takes its declared null_default, never an implicit zero.
"""

from __future__ import annotations

from dataclasses import dataclass

from .errors import UsageError

AGGREGATIONS = ("count", "sum", "distinct_days", "days_since_last")


@dataclass(frozen=True)
class FeatureSpec:
    name: str
    source: str  # event type, or "any"
    agg: str
    window_days: int | None  # None for days_since_last
    null_default: float
    description: str

    def __post_init__(self):
        if self.agg not in AGGREGATIONS:
            raise UsageError(f"unknown aggregation {self.agg!r} in spec {self.name!r}")
        if self.agg == "days_since_last":
            if self.window_days is not None:
                raise UsageError(f"{self.name}: days_since_last takes no window")
        elif self.window_days is None or self.window_days < 1:
            raise UsageError(f"{self.name}: window_days must be >= 1")

    def window_start(self, cutoff_day: int) -> int:
        """First day inside the window: cutoff - W + 1, inclusive by declaration."""
        if self.window_days is None:
            raise UsageError(f"{self.name}: no window defined")
        return cutoff_day - self.window_days + 1


SPECS: tuple[FeatureSpec, ...] = (
    FeatureSpec("logins_30d", "login", "count", 30, 0.0,
                "login events in the 30 days ending at cutoff, inclusive"),
    FeatureSpec("watch_minutes_7d", "watch", "sum", 7, 0.0,
                "minutes watched in the 7 days ending at cutoff, inclusive"),
    FeatureSpec("tickets_90d", "ticket", "count", 90, 0.0,
                "support tickets in the 90 days ending at cutoff, inclusive"),
    FeatureSpec("active_days_30d", "any", "distinct_days", 30, 0.0,
                "distinct days with any event in the 30 days ending at cutoff"),
    FeatureSpec("days_since_last_login", "login", "days_since_last", None, 999.0,
                "cutoff minus the most recent login day; 999 if the user never logged in"),
)


def spec_by_name(name: str) -> FeatureSpec:
    for spec in SPECS:
        if spec.name == name:
            return spec
    raise UsageError(f"no spec named {name!r}")
