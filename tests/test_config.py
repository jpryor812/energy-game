from pathlib import Path

import pytest
import yaml

from sim import config
from sim.config import ConfigError


def test_config_hash_is_stable():
    assert config.load().hash == config.load().hash


@pytest.fixture
def data_copy(tmp_path, fixture_dir) -> Path:
    for path in fixture_dir.glob("*.yaml"):
        (tmp_path / path.name).write_text(path.read_text())
    return tmp_path


def _edit(path: Path, fn) -> None:
    data = yaml.safe_load(path.read_text())
    fn(data)
    path.write_text(yaml.safe_dump(data))


def test_rejects_bare_number(data_copy):
    d = data_copy
    _edit(d / "tuning.yaml", lambda t: t["time"].__setitem__("magic", 3.5))
    with pytest.raises(ConfigError, match="bare number"):
        config.load(d)


def test_rejects_bad_status(data_copy):
    d = data_copy
    _edit(d / "tuning.yaml", lambda t: t["time"]["turns"].__setitem__("status", "guess"))
    with pytest.raises(ConfigError, match="status"):
        config.load(d)


def test_rejects_missing_note(data_copy):
    d = data_copy
    _edit(d / "tuning.yaml", lambda t: t["time"]["turns"].pop("note"))
    with pytest.raises(ConfigError, match="note"):
        config.load(d)


def test_rejects_unknown_personality(data_copy):
    d = data_copy
    _edit(d / "countries.yaml", lambda c: c["nations"]["AAA"].__setitem__("personality", "chaotic"))
    with pytest.raises(ConfigError, match="personality"):
        config.load(d)


def test_rejects_missing_file(data_copy):
    d = data_copy
    (d / "techs.yaml").unlink()
    with pytest.raises(ConfigError, match="missing"):
        config.load(d)


def test_value_lookup_errors(cfg):
    with pytest.raises(KeyError):
        cfg.value("tuning", "time.nope")
    with pytest.raises(KeyError):
        cfg.value("tuning", "time")  # a section, not a tunable


def test_rejects_missing_required_tunable(data_copy):
    _edit(data_copy / "countries.yaml", lambda c: c["nations"]["AAA"]["trend"].pop("g0_end"))
    with pytest.raises(ConfigError, match="g0_end"):
        config.load(data_copy)


def test_rejects_bau_mix_not_summing_to_one(data_copy):
    def bad(c):
        c["nations"]["AAA"]["bau"]["mix"]["coal"]["value"] = 0.9

    _edit(data_copy / "countries.yaml", bad)
    with pytest.raises(ConfigError, match="sum"):
        config.load(data_copy)
