"""Properties of the generator and the two-commit Delta table."""

import pytest

from churn_feature_referee.errors import DataError, UsageError
from churn_feature_referee.events import (
    Event,
    generate_events,
    load_events,
    read_meta,
    write_delta,
)

CUTOFF = 400


@pytest.fixture(scope="module")
def events():
    return generate_events(seed=11, n_users=40, cutoff_day=CUTOFF)


@pytest.fixture(scope="module")
def table(tmp_path_factory, events):
    path = tmp_path_factory.mktemp("delta") / "t"
    meta = write_delta(events, path, cutoff_day=CUTOFF)
    return path, meta


def test_the_same_seed_produces_identical_event_logs(events):
    assert generate_events(seed=11, n_users=40, cutoff_day=CUTOFF) == events


def test_different_seeds_produce_different_event_logs(events):
    assert generate_events(seed=12, n_users=40, cutoff_day=CUTOFF) != events


def test_user_zero_never_logs_in(events):
    assert not any(e.etype == "login" for e in events if e.user_id == "u0000")


def test_user_one_logs_in_exactly_on_the_cutoff_day(events):
    days = [e.day for e in events if e.user_id == "u0001" and e.etype == "login"]
    assert days == [CUTOFF]


def test_user_two_brackets_the_thirty_day_window_boundary(events):
    days = sorted(e.day for e in events if e.user_id == "u0002" and e.etype == "login")
    assert days == [CUTOFF - 30, CUTOFF - 29]


def test_user_three_only_login_arrives_after_the_cutoff(events):
    days = [e.day for e in events if e.user_id == "u0003" and e.etype == "login"]
    assert days and all(d > CUTOFF for d in days)


def test_some_late_arriving_events_exist(events):
    assert any(e.day > CUTOFF for e in events)


def test_too_few_users_to_hold_the_hard_cases_is_refused():
    with pytest.raises(UsageError, match="n_users"):
        generate_events(seed=1, n_users=5)


def test_a_history_shorter_than_the_longest_window_is_refused():
    with pytest.raises(UsageError, match="history_days"):
        generate_events(seed=1, history_days=30)


def test_version_zero_is_exactly_the_at_or_before_cutoff_snapshot(table, events):
    path, meta = table
    snapshot = load_events(path, version=meta["snapshot_version"])
    assert snapshot == sorted(
        [e for e in events if e.day <= CUTOFF],
        key=lambda e: (e.user_id, e.day, e.etype, e.minutes),
    )


def test_the_latest_version_contains_the_late_events_too(table, events):
    path, _meta = table
    latest = load_events(path)
    assert len(latest) == len(events)
    assert any(e.day > CUTOFF for e in latest)


def test_meta_counts_match_what_was_written(table, events):
    _path, meta = table
    assert meta["n_snapshot_events"] == sum(1 for e in events if e.day <= CUTOFF)
    assert meta["n_late_events"] == sum(1 for e in events if e.day > CUTOFF)
    assert meta["n_users"] == len({e.user_id for e in events})


def test_meta_round_trips_through_the_sidecar_file(table):
    path, meta = table
    assert read_meta(path) == meta


def test_reading_meta_from_a_plain_directory_is_a_data_error(tmp_path):
    with pytest.raises(DataError, match="missing _referee_meta"):
        read_meta(tmp_path)


def test_loading_a_missing_table_is_a_data_error(tmp_path):
    with pytest.raises(DataError, match="cannot open Delta table"):
        load_events(tmp_path / "ghost")


def test_writing_over_a_non_empty_directory_is_refused(tmp_path, events):
    target = tmp_path / "t"
    target.mkdir()
    (target / "junk.txt").write_text("x")
    with pytest.raises(UsageError, match="non-empty"):
        write_delta(events, target, cutoff_day=CUTOFF)


def test_a_log_with_no_snapshot_events_is_refused(tmp_path):
    late_only = [Event("u0", CUTOFF + 1, "login", 0.0)]
    with pytest.raises(UsageError, match="nothing to snapshot"):
        write_delta(late_only, tmp_path / "t", cutoff_day=CUTOFF)


def test_events_load_back_sorted_and_typed(table):
    path, _meta = table
    loaded = load_events(path)
    assert loaded == sorted(loaded, key=lambda e: (e.user_id, e.day, e.etype, e.minutes))
    assert all(isinstance(e.day, int) and isinstance(e.minutes, float) for e in loaded)


def test_a_corrupt_meta_sidecar_is_a_data_error(tmp_path, events):
    target = tmp_path / "t"
    write_delta(events, target, cutoff_day=CUTOFF)
    (target / "_referee_meta.json").write_text("{broken")
    with pytest.raises(DataError, match="corrupt meta"):
        read_meta(target)


def test_the_event_log_is_sorted_by_user_then_day(events):
    assert events == sorted(events, key=lambda e: (e.user_id, e.day, e.etype, e.minutes))


def test_watch_events_carry_minutes_and_other_events_do_not(events):
    assert all((e.minutes > 0) == (e.etype == "watch") for e in events)


def test_the_default_corpus_shape_is_what_the_readme_describes():
    events = generate_events(seed=11, n_users=120, cutoff_day=CUTOFF)
    assert len({e.user_id for e in events}) == 120
    assert sum(1 for e in events if e.day <= CUTOFF) == 1522
    assert sum(1 for e in events if e.day > CUTOFF) == 29
