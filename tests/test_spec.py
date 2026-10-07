"""Properties of the feature spec: the declared semantics everything serves."""

import pytest

from churn_feature_referee.errors import UsageError
from churn_feature_referee.spec import SPECS, FeatureSpec, spec_by_name


def test_the_window_covers_exactly_window_days_days():
    spec = spec_by_name("logins_30d")
    start = spec.window_start(400)
    assert 400 - start + 1 == 30


def test_the_window_start_is_cutoff_minus_window_plus_one():
    assert spec_by_name("logins_30d").window_start(400) == 371


def test_every_spec_has_a_unique_name():
    names = [s.name for s in SPECS]
    assert len(names) == len(set(names))


def test_the_spec_set_holds_five_features():
    assert len(SPECS) == 5


def test_days_since_last_login_declares_a_nonzero_null_default():
    # 0 would mean "logged in today", which is the serving bug this corpus
    # exists to catch; the spec must not share it.
    assert spec_by_name("days_since_last_login").null_default == 999.0


def test_an_unknown_aggregation_is_refused():
    with pytest.raises(UsageError, match="unknown aggregation"):
        FeatureSpec("x", "login", "median", 7, 0.0, "")


def test_days_since_last_with_a_window_is_refused():
    with pytest.raises(UsageError, match="takes no window"):
        FeatureSpec("x", "login", "days_since_last", 7, 0.0, "")


def test_a_windowed_aggregation_without_a_window_is_refused():
    with pytest.raises(UsageError, match="window_days"):
        FeatureSpec("x", "login", "count", None, 0.0, "")


def test_a_window_below_one_day_is_refused():
    with pytest.raises(UsageError, match="window_days"):
        FeatureSpec("x", "login", "count", 0, 0.0, "")


def test_window_start_on_a_windowless_spec_is_refused():
    with pytest.raises(UsageError, match="no window"):
        spec_by_name("days_since_last_login").window_start(400)


def test_looking_up_a_missing_spec_is_refused():
    with pytest.raises(UsageError, match="no spec named"):
        spec_by_name("ghost_feature")
