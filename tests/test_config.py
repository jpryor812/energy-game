from pathlib import Path

import pytest
import yaml

from sim import config
from sim.config import ConfigError


def test_default_data_loads():
    cfg = config.load()
    assert len(cfg.nation_ids) == 16
    assert cfg.playable_ids == ["CHN", "EUU", "IND", "RUS", "USA", "VNM"]
    assert cfg.value("tuning", "time.turns") == 100
    assert "solar" in cfg.source_ids


def test_config_hash_is_stable():
    assert config.load().hash == config.load().hash


def _copy_data(tmp_path: Path) -> Path:
    for path in config.DEFAULT_DATA_DIR.glob("*.yaml"):
        (tmp_path / path.name).write_text(path.read_text())
    return tmp_path


def _edit(path: Path, fn) -> None:
    data = yaml.safe_load(path.read_text())
    fn(data)
    path.write_text(yaml.safe_dump(data))


def test_rejects_bare_number(tmp_path):
    d = _copy_data(tmp_path)
    _edit(d / "tuning.yaml", lambda t: t["time"].__setitem__("magic", 3.5))
    with pytest.raises(ConfigError, match="bare number"):
        config.load(d)


def test_rejects_bad_status(tmp_path):
    d = _copy_data(tmp_path)
    _edit(d / "tuning.yaml", lambda t: t["time"]["turns"].__setitem__("status", "guess"))
    with pytest.raises(ConfigError, match="status"):
        config.load(d)


def test_rejects_missing_note(tmp_path):
    d = _copy_data(tmp_path)
    _edit(d / "tuning.yaml", lambda t: t["time"]["turns"].pop("note"))
    with pytest.raises(ConfigError, match="note"):
        config.load(d)


def test_rejects_unknown_personality(tmp_path):
    d = _copy_data(tmp_path)
    _edit(d / "countries.yaml", lambda c: c["nations"]["IND"].__setitem__("personality", "chaotic"))
    with pytest.raises(ConfigError, match="personality"):
        config.load(d)


def test_rejects_missing_file(tmp_path):
    d = _copy_data(tmp_path)
    (d / "techs.yaml").unlink()
    with pytest.raises(ConfigError, match="missing"):
        config.load(d)


def test_value_lookup_errors():
    cfg = config.load()
    with pytest.raises(KeyError):
        cfg.value("tuning", "time.nope")
    with pytest.raises(KeyError):
        cfg.value("tuning", "time")  # a section, not a tunable
