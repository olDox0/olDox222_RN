import array
import sqlite3

import engine.tools.local_index as li


def test_search_local_works_without_inverted_index(monkeypatch, tmp_path) -> None:
    index_dir = tmp_path / "index"
    index_dir.mkdir()

    source_id = "softwareengineering_stackexchange_com_en_all_2026_02"
    db_path = index_dir / f"{source_id}.db"

    con = sqlite3.connect(db_path)
    con.execute("CREATE TABLE pages (id INTEGER PRIMARY KEY, title TEXT, path TEXT, content_hash TEXT)")
    con.execute("CREATE TABLE content_pool (hash TEXT PRIMARY KEY, token_blob BLOB)")
    con.execute("CREATE TABLE title_trigrams (trigram TEXT, doc_id INTEGER)")

    payload = array.array("i", [1, 2, 3]).tobytes()
    token_blob = li._compress(payload)
    con.execute("INSERT INTO content_pool (hash, token_blob) VALUES (?, ?)", ("h1", token_blob))
    con.execute(
        "INSERT INTO pages (id, title, path, content_hash) VALUES (?,?,?,?)",
        (1, "Python quicksort", "Python_quicksort", "h1"),
    )
    con.commit()
    con.close()

    monkeypatch.setattr(li, "INDEX_DIR", index_dir)
    monkeypatch.setattr(li.TokenizerBridge, "bytes_to_text", classmethod(lambda cls, _b: "Python quicksort example"))
    li.LocalIndexCache.evict(source_id)

    results = li.search_local("python quicksort", source_id=source_id, limit=3)

    assert results
    assert results[0].title == "Python quicksort"
