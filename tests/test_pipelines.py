"""The three implementations against hand-computed boundary cases.

The named users exist so these tests read as the spec's worked examples:
u0001 (cutoff-day-only login) is the exclusive_window bait, u0002 (logins on
the window's first day and the day before) is the off-by-one bait, u0000
(never logs in) is the null-default bait, u0003 (login only after cutoff) is
the point-in-time bait.
"""

import pytest

from churn_feature_referee.errors import UsageError
from churn_feature_referee.events import Event, generate_events, load_events, write_delta
from churn_feature_referee.offline import OfflinePipeline
from churn_feature_referee.referee import referee_compute, referee_value
from churn_feature_referee.serving import ServingPipeline
from churn_feature_referee.spec import SPECS, spec_by_name

CUTOFF = 400


@pytest.fixture(scope="module")
def table(tmp_path_factory):
    events = generate_events(seed=11, n_users=40, cutoff_day=CUTOFF)
    path = tmp_path_factory.mktemp("delta") / "t"
    write_delta(events, path, cutoff_day=CUTOFF)
    return path


@pytest.fixture(scope="module")
def snapshot(table):
    return load_events(table, version=0)


# Referee against hand-computed values -----------------------------------

def test_referee_counts_a_cutoff_day_login_as_inside_the_window():
    rows = [Event("u", CUTOFF, "login", 0.0)]
    assert referee_value(rows, spec_by_name("logins_30d"), CUTOFF) == 1.0


def test_referee_counts_the_window_first_day_and_not_the_day_before():
    spec = spec_by_name("logins_30d")
    inside = [Event("u", CUTOFF - 29, "login", 0.0)]
    outside = [Event("u", CUTOFF - 30, "login", 0.0)]
    assert referee_value(inside, spec, CUTOFF) == 1.0
    assert referee_value(outside, spec, CUTOFF) == 0.0


def test_referee_never_counts_an_event_after_the_cutoff():
    rows = [Event("u", CUTOFF + 1, "login", 0.0)]
    assert referee_value(rows, spec_by_name("logins_30d"), CUTOFF) == 0.0
    assert referee_value(rows, spec_by_name("days_since_last_login"), CUTOFF) == 999.0


def test_referee_days_since_last_login_on_the_cutoff_day_is_zero():
    rows = [Event("u", CUTOFF, "login", 0.0)]
    assert referee_value(rows, spec_by_name("days_since_last_login"), CUTOFF) == 0.0


def test_referee_uses_the_declared_null_default_for_a_never_login_user():
    rows = [Event("u", CUTOFF - 3, "watch", 30.0)]
    assert referee_value(rows, spec_by_name("days_since_last_login"), CUTOFF) == 999.0


def test_referee_sums_minutes_only_inside_the_seven_day_window():
    spec = spec_by_name("watch_minutes_7d")
    rows = [Event("u", CUTOFF - 6, "watch", 10.0),   # first day inside
            Event("u", CUTOFF - 7, "watch", 100.0),  # one day outside
            Event("u", CUTOFF, "watch", 5.0)]
    assert referee_value(rows, spec, CUTOFF) == 15.0


def test_referee_distinct_days_counts_days_not_events():
    spec = spec_by_name("active_days_30d")
    rows = [Event("u", CUTOFF, "login", 0.0), Event("u", CUTOFF, "watch", 9.0),
            Event("u", CUTOFF - 1, "ticket", 0.0)]
    assert referee_value(rows, spec, CUTOFF) == 2.0


def test_referee_compute_covers_every_user_feature_pair(snapshot):
    values = referee_compute(snapshot, SPECS, CUTOFF)
    users = {e.user_id for e in snapshot}
    assert len(values) == len(users) * len(SPECS)


# The three implementations agree when nothing is broken ------------------

def test_clean_offline_matches_the_referee_everywhere(table, snapshot):
    offline = OfflinePipeline().compute(table, SPECS, CUTOFF)
    referee = referee_compute(snapshot, SPECS, CUTOFF)
    assert offline == referee


def test_clean_serving_matches_the_referee_everywhere(snapshot):
    serving = ServingPipeline().compute(snapshot, SPECS, CUTOFF)
    referee = referee_compute(snapshot, SPECS, CUTOFF)
    assert serving == referee


# Defects do exactly what their names say ---------------------------------

def test_exclusive_window_drops_only_cutoff_day_events(snapshot):
    clean = ServingPipeline().compute(snapshot, SPECS, CUTOFF)
    buggy = ServingPipeline({"exclusive_window"}).compute(snapshot, SPECS, CUTOFF)
    changed = {k for k in clean if clean[k] != buggy[k]}
    cutoff_day_users = {e.user_id for e in snapshot if e.day == CUTOFF}
    assert changed
    assert {u for u, _f in changed} <= cutoff_day_users
    assert ("u0001", "logins_30d") in changed


def test_null_default_zero_changes_only_never_login_users(snapshot):
    clean = ServingPipeline().compute(snapshot, SPECS, CUTOFF)
    buggy = ServingPipeline({"null_default_zero"}).compute(snapshot, SPECS, CUTOFF)
    changed = {k for k in clean if clean[k] != buggy[k]}
    assert changed
    assert all(f == "days_since_last_login" for _u, f in changed)
    assert buggy[("u0000", "days_since_last_login")] == 0.0


def test_the_leak_anchors_windows_at_the_newest_visible_day(table, snapshot):
    leaky = OfflinePipeline({"leak_future"}).compute(table, SPECS, CUTOFF)
    latest_day = max(e.day for e in load_events(table))
    assert latest_day > CUTOFF
    # u0003's only login is after the cutoff: a correct pipeline reports the
    # null default, the leaky one sees the login relative to its new anchor.
    assert leaky[("u0003", "days_since_last_login")] == float(latest_day - (CUTOFF + 2))


def test_the_leak_shifts_window_boundaries_forward(table, snapshot):
    clean = OfflinePipeline().compute(table, SPECS, CUTOFF)
    leaky = OfflinePipeline({"leak_future"}).compute(table, SPECS, CUTOFF)
    # u0002's login on the window's first day falls out once the anchor moves.
    key = ("u0002", "logins_30d")
    assert clean[key] == 1.0
    assert leaky[key] == 0.0


def test_tz_shift_moves_a_cutoff_day_login_out_of_every_window(table):
    shifted = OfflinePipeline({"tz_shift"}).compute(table, SPECS, CUTOFF)
    assert shifted[("u0001", "logins_30d")] == 0.0


def test_offline_and_serving_share_the_exclusive_window_bug_bit_for_bit(table, snapshot):
    offline = OfflinePipeline({"exclusive_window"}).compute(table, SPECS, CUTOFF)
    serving = ServingPipeline({"exclusive_window"}).compute(snapshot, SPECS, CUTOFF)
    assert offline == serving


def test_unknown_defect_names_are_refused_on_both_sides():
    with pytest.raises(UsageError, match="unknown offline defects"):
        OfflinePipeline({"ghost"})
    with pytest.raises(UsageError, match="unknown serving defects"):
        ServingPipeline({"ghost"})


def test_serving_refuses_a_state_containing_future_events():
    with pytest.raises(UsageError, match="no future"):
        ServingPipeline().compute([Event("u", CUTOFF + 1, "login", 0.0)], SPECS, CUTOFF)
