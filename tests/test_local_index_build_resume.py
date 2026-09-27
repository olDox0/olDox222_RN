import sqlite3
import types

import engine.tools.local_index as li


class _FakeVocab:
    def tokenize(self, _b, add_bos=False):
        return [1, 2, 3]


def test_build_index_resumes_from_in_progress_meta(monkeypatch, tmp_path) -> None:
    index_dir = tmp_path / "index"
    zim_dir = tmp_path / "zim"
    index_dir.mkdir()
    zim_dir.mkdir()

    source_id = "resume_test"
    db_path = index_dir / f"{source_id}.db"

    con = sqlite3.connect(db_path)
    con.execute("CREATE TABLE pages (id INTEGER PRIMARY KEY, title TEXT, path TEXT, content_hash TEXT)")
    con.execute("CREATE TABLE content_pool (hash TEXT PRIMARY KEY, token_blob BLOB)")
    con.execute("CREATE TABLE title_trigrams (trigram TEXT, doc_id INTEGER)")
    con.execute("CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT)")
    con.execute("INSERT INTO meta (key, value) VALUES ('build_status', 'in_progress')")
    con.execute("INSERT INTO meta (key, value) VALUES ('build_scanned_entries', '123')")
    con.execute("INSERT INTO meta (key, value) VALUES ('build_docs_processed', '1')")
    con.execute("INSERT INTO pages (id, title, path, content_hash) VALUES (1, 'old', 'old', 'h1')")
    con.commit()
    con.close()

    zim_file = zim_dir / "resume.zim"
    zim_file.write_bytes(b"dummy")

    monkeypatch.setattr(li, "INDEX_DIR", index_dir)
    monkeypatch.setattr(li, "ZIM_DIR", zim_dir)
    monkeypatch.setattr(li.TokenizerBridge, "get_vocab", classmethod(lambda cls: _FakeVocab()))
    monkeypatch.setattr(li, "_iter_zim_entries", lambda *a, **k: iter([]))
    monkeypatch.setitem(__import__("sys").modules, "pyzim", types.SimpleNamespace())

    out_db = li.build_index(str(zim_file), source_id=source_id, verbose=False)

    assert out_db == db_path

    con = sqlite3.connect(db_path)
    meta = dict(con.execute("SELECT key, value FROM meta").fetchall())
    page_count = con.execute("SELECT COUNT(*) FROM pages").fetchone()[0]
    con.close()

    assert meta["build_status"] == "completed"
    assert int(meta["build_scanned_entries"]) >= 123
    assert int(meta["build_docs_processed"]) >= 1
    assert page_count == 1
