import pytest

from sim import rng


def draws(*args, n=5):
    r = rng.stream(*args)
    return [r.random() for _ in range(n)]


def test_same_inputs_same_draws():
    assert draws(1, "shocks", 3, "IND") == draws(1, "shocks", 3, "IND")


def test_inputs_separate_streams():
    base = draws(1, "shocks", 3, "IND")
    assert draws(2, "shocks", 3, "IND") != base
    assert draws(1, "events", 3, "IND") != base
    assert draws(1, "shocks", 4, "IND") != base
    assert draws(1, "shocks", 3, "CHN") != base


def test_key_boundaries_are_unambiguous():
    assert rng.derive_seed(1, "shocks", "12", "3") != rng.derive_seed(1, "shocks", "1", "23")


def test_known_value():
    # Pins the derivation so a change to it is deliberate (it would change every run's output).
    assert rng.derive_seed(1, "events") == 10099430130475478387


def test_unknown_stream_rejected():
    with pytest.raises(ValueError):
        rng.stream(1, "typo")
