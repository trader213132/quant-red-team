from pathlib import Path

from qrt.config import code_hash, config_hash, load_config

DEV = Path(__file__).parent.parent / "configs" / "dev.toml"


def test_loads_dev_config():
    cfg = load_config(DEV)
    assert cfg.markets["null"].kind == "null"
    assert cfg.markets["delisting"].n_assets == 50
    assert cfg.markets["trend"].name == "trend"
    assert cfg.researchers[0] == "honest_null"
    assert cfg.audits.placebo_reps == 49
    assert cfg.run.target_claims == 30


def test_config_hash_is_stable_and_sensitive(tmp_path):
    text = DEV.read_text(encoding="utf-8")
    a = tmp_path / "a.toml"
    b = tmp_path / "b.toml"
    a.write_text(text, encoding="utf-8")
    b.write_text(text.replace("seed = 20261007", "seed = 1"), encoding="utf-8")
    assert config_hash(load_config(a)) == config_hash(load_config(DEV))
    assert config_hash(load_config(a)) != config_hash(load_config(b))


def test_code_hash_is_hex():
    h = code_hash()
    assert len(h) == 64 and int(h, 16) >= 0


def test_code_hash_ignores_line_endings(tmp_path, monkeypatch):
    import qrt.config as config
    (tmp_path / "a.py").write_bytes(b"x = 1\nprint(x)\n")
    monkeypatch.setattr(config, "PACKAGE_DIR", tmp_path)
    lf = config.code_hash()
    (tmp_path / "a.py").write_bytes(b"x = 1\r\nprint(x)\r\n")
    assert config.code_hash() == lf
    (tmp_path / "a.py").write_bytes(b"x = 2\nprint(x)\n")
    assert config.code_hash() != lf
