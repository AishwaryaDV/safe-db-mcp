import sqlite3

import pytest

from safedb import db


@pytest.fixture
def sample_db(tmp_path):
    path = tmp_path / "sample.sqlite"
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE artist (id INTEGER PRIMARY KEY, name TEXT NOT NULL);
        CREATE TABLE album (
            id INTEGER PRIMARY KEY,
            title TEXT NOT NULL,
            artist_id INTEGER REFERENCES artist(id)
        );
        INSERT INTO artist (id, name) VALUES (1, 'AC/DC'), (2, 'Aerosmith');
        INSERT INTO album (id, title, artist_id) VALUES (1, 'Let There Be Rock', 1);
        """
    )
    conn.commit()
    conn.close()
    return path


@pytest.mark.unit
def test_open_readonly_rejects_writes(sample_db):
    conn = db.open_readonly(sample_db)
    with pytest.raises(sqlite3.OperationalError):
        conn.execute("INSERT INTO artist (id, name) VALUES (3, 'x')")
    conn.close()


@pytest.mark.unit
def test_open_readonly_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        db.open_readonly(tmp_path / "nope.sqlite")


@pytest.mark.unit
def test_introspection(sample_db):
    conn = db.open_readonly(sample_db)
    assert db.list_tables(conn) == ["album", "artist"]
    assert db.table_count(conn) == 2
    assert db.row_count(conn, "artist") == 2

    cols = db.columns(conn, "artist")
    assert {"name": "id", "type": "INTEGER", "primary_key": True, "not_null": False} in cols
    assert {"name": "name", "type": "TEXT", "primary_key": False, "not_null": True} in cols

    fks = db.foreign_keys(conn, "album")
    assert fks == [{"column": "artist_id", "ref_table": "artist", "ref_column": "id"}]
    conn.close()


@pytest.mark.unit
def test_sample_rows_and_truncation(sample_db):
    conn = db.open_readonly(sample_db)
    rows = db.sample_rows(conn, "artist", 3)
    assert [r[1] for r in rows] == ["AC/DC", "Aerosmith"]
    assert db.sample_rows(conn, "artist", 0) == []

    long_rows = db.sample_rows(conn, "album", 1, cell_limit=5)
    assert long_rows[0][1] == "Let T…"  # "Let There Be Rock" cut to 5 chars + ellipsis
    conn.close()
