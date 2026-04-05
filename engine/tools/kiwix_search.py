# engine/tools/kiwix_search.py
import libzim
# [DOX-UNUSED] from pathlib import Path

class KiwixSearcher:
    def __init__(self, zim_path: str):
        self._archive = libzim.Archive(zim_path)
        self._searcher = libzim.Searcher(self._archive)

    def search(self, query: str, max_results: int = 3) -> list[dict]:
        sq = libzim.Query().set_query(query)
        results = self._searcher.search(sq)
        out = []
        for r in results.getResults(0, max_results):
            entry = self._archive.get_entry_by_path(r)
            out.append({
                "title": entry.title,
                "path": r,
                "snippet": _extract_text(entry, max_chars=1500),
            })
        return out