import pytest

from safedb.config import AppConfig, Limits, load_config


@pytest.mark.unit
def test_load_config_reads_chinook(tmp_path):
    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        "databases:\n"
        "  - name: chinook\n"
        "    path: data/chinook/Chinook_Sqlite.sqlite\n"
        "    description: Music store\n"
        "limits:\n"
        "  max_rows_cap: 500\n"
        "audit_db: data/audit.sqlite\n",
        encoding="utf-8",
    )
    config = load_config(cfg)
    assert config.database("chinook").path == "data/chinook/Chinook_Sqlite.sqlite"
    assert config.limits.max_rows_cap == 500
    # Unset limits fall back to defaults.
    assert config.limits.max_rows_default == 100


@pytest.mark.unit
def test_unknown_database_lists_known_names():
    config = AppConfig(databases=[{"name": "chinook", "path": "x"}], limits=Limits())
    with pytest.raises(KeyError, match="chinook"):
        config.database("nope")
