# -*- coding: utf-8 -*-
# engine/tools/inverted_index.py
"""
Índice Invertido com varint + delta encoding.

Formato em disco (fmt=2):
  postings.bin  — posting lists length-prefixed + delta varint
  vocab.bin     — array binário de (token_id: u32, offset: u64) ordenado por token_id
  meta.json     — doc_count e versão do formato

Mudanças em relação à versão anterior (fmt=1):

  1. vocab.json → vocab.bin
     JSON de 5M entradas ocupa ~150MB e leva segundos para carregar.
     vocab.bin usa struct.pack de pares (u32, u64) = 12 bytes cada.
     Resultado: ~60MB, carregamento ~10x mais rápido, busca por bisect O(log n).

  2. Sentinel-0 → length-prefix
     O sentinel delta=0 parava a leitura prematuramente em casos frágeis.
     Length-prefix é explícito: [n_docs varint][delta1 varint][delta2 varint]...

  3. mmap em postings.bin
     Carregamento anterior: f.read() inteiro em RAM (~300MB para Wikipedia).
     mmap: o SO pagina apenas os blocos lidos pela query atual.
     Resultado: RAM cai de ~300MB para ~alguns MB por query.

  4. Filtro IDF em search()
     Tokens em >IDF_MAX_FRACTION do corpus são stop words implícitas.
     Ignorá-los acelera a query e melhora relevância.

Compatibilidade: fmt=1 (vocab.json + sentinel-0) ainda é lido pelo Searcher.
"""

from __future__ import annotations

import bisect
import json
import mmap
import math
import struct
from collections import defaultdict
from pathlib import Path

# Tokens presentes em mais de IDF_MAX_FRACTION dos documentos são stop words.
IDF_MAX_FRACTION: float = 0.40

# Formato do vocab binário: (token_id u32, byte_offset u64) = 12 bytes por entrada.
_VOCAB_ENTRY_FMT_V3 = "<IQI"   # token_id(u32), offset(u64), df(u32)
_VOCAB_ENTRY_SIZE_V3 = struct.calcsize(_VOCAB_ENTRY_FMT_V3)  # 4+8+4 = 16 bytes



# ---------------------------------------------------------------------------
# Varint encoding
# ---------------------------------------------------------------------------

def encode_varint(n: int) -> bytes:
    """Codifica inteiro não-negativo em varint (1-9 bytes)."""
    out = bytearray()
    while True:
        b = n & 0x7F
        n >>= 7
        if n:
            out.append(b | 0x80)
        else:
            out.append(b)
            break
    return bytes(out)


def decode_varint(data: bytes | mmap.mmap, pos: int) -> tuple[int, int]:
    """Decodifica varint em data[pos:]. Retorna (valor, próxima_posição)."""
    shift = 0
    result = 0
    while True:
        b = data[pos]
        pos += 1
        result |= (b & 0x7F) << shift
        if not b & 0x80:
            break
        shift += 7
    return result, pos


# ---------------------------------------------------------------------------
# Builder
# ---------------------------------------------------------------------------

class InvertedIndexBuilder:
    def __init__(self) -> None:
        # postings: token_id -> list of (doc_id, [positions...])
        self.postings: dict[int, dict[int, list[int]]] = defaultdict(lambda: defaultdict(list))
        self.doc_count: int = 0
        # store document lengths for avgdl
        self._doc_lengths: dict[int, int] = {}

    def add_document(self, doc_id: int, tokens) -> None:
        """tokens: iterable of term ids (int). We record positions starting at 1."""
        pos = 1
        length = 0
        for t in tokens:
            t = int(t)
            self.postings[t][doc_id].append(pos)
            pos += 1
            length += 1
        self._doc_lengths[doc_id] = length
        if doc_id > self.doc_count:
            self.doc_count = doc_id

    def finalize(self) -> None:
        # sort positions and ensure posting doc-ids are sorted lists
        for token, docs in list(self.postings.items()):
            for d in list(docs.keys()):
                docs[d].sort()

    def write(self, path: Path) -> None:
        path.mkdir(parents=True, exist_ok=True)
        vocab_entries: list[tuple[int, int, int]] = []  # token_id, offset, df
        postings_buf = bytearray()

        # write postings: tokens sorted by token_id
        for token_id in sorted(self.postings.keys()):
            docs_map = self.postings[token_id]
            docs_items = sorted(docs_map.items())  # list of (doc_id, positions)
            offset = len(postings_buf)
            df = len(docs_items)
            vocab_entries.append((int(token_id), offset, df))

            # length-prefix (n_docs)
            postings_buf += encode_varint(df)
            prev_doc = 0
            for doc_id, positions in docs_items:
                postings_buf += encode_varint(doc_id - prev_doc)
                prev_doc = doc_id
                # tf
                tf = len(positions)
                postings_buf += encode_varint(tf)
                # positions: delta-encode within document
                prev_pos = 0
                for p in positions:
                    postings_buf += encode_varint(p - prev_pos)
                    prev_pos = p

        with open(path / "postings.bin", "wb") as f:
            f.write(postings_buf)

        # vocab.bin v3: token_id(u32), offset(u64), df(u32)
        with open(path / "vocab.bin", "wb") as f:
            for token_id, offset, df in vocab_entries:
                f.write(struct.pack(_VOCAB_ENTRY_FMT_V3, token_id, offset, df))

        # meta.json: include doc_count, avgdl, fmt
        total_dl = sum(self._doc_lengths.values()) or 0
        doc_count = max(1, len(self._doc_lengths))
        avgdl = total_dl / doc_count if doc_count else 0.0
        with open(path / "meta.json", "w", encoding="utf-8") as f:
            json.dump({"doc_count": doc_count, "avgdl": avgdl, "fmt": 3}, f)

class DocumentStore:
    """Armazena documentos em docs.bin como: len(varint) + utf8 bytes.
       Também indexa offsets para leitura rápida e snippet extraction.
    """
    def __init__(self, path: Path):
        self.path = path / "docs.bin"
        if self.path.exists():
            self._f = open(self.path, "rb")
            self._m = mmap.mmap(self._f.fileno(), 0, access=mmap.ACCESS_READ)
        else:
            # empty store
            self._f = None
            self._m = None

    def get_doc_text(self, offset: int, length: int) -> str:
        if self._m is None:
            return ""
        data = self._m[offset: offset + length]
        return data.decode("utf-8", errors="replace")

    def close(self):
        try:
            if self._m: self._m.close()
        except:
            pass
        try:
            if self._f: self._f.close()
        except:
            pass
            

# ---------------------------------------------------------------------------
# Searcher
# ---------------------------------------------------------------------------

# --- Searcher update ---
class InvertedIndexSearcher:
    def __init__(self, path: Path) -> None:
        with open(path / "meta.json", encoding="utf-8") as f:
            self._meta = json.load(f)

        fmt = self._meta.get("fmt", 1)
        self._fmt = fmt
        self._legacy = fmt < 2

        if fmt >= 3 and (path / "vocab.bin").exists():
            self._load_vocab_binary_v3(path / "vocab.bin")
        elif fmt >= 2 and (path / "vocab.bin").exists():
            self._load_vocab_binary(path / "vocab.bin")
        else:
            self._load_vocab_json(path / "vocab.json")
            self._legacy = True

        self._pf = open(path / "postings.bin", "rb")
        self._postings = mmap.mmap(self._pf.fileno(), 0, access=mmap.ACCESS_READ)

        # DocumentStore for snippets (optional)
        self._doc_store = DocumentStore(path)

        self.N = max(1, int(self._meta.get("doc_count", 1)))
        self.avgdl = float(self._meta.get("avgdl", 1.0))
        # BM25 params
        self.k1 = 1.5
        self.b = 0.75

    def _load_vocab_binary_v3(self, vocab_path: Path) -> None:
        raw = vocab_path.read_bytes()
        n = len(raw) // _VOCAB_ENTRY_SIZE_V3
        self._vocab_ids = []
        self._vocab_offsets = []
        self._vocab_dfs = []
        for i in range(n):
            tid, off, df = struct.unpack_from(_VOCAB_ENTRY_FMT_V3, raw, i * _VOCAB_ENTRY_SIZE_V3)
            self._vocab_ids.append(tid)
            self._vocab_offsets.append(off)
            self._vocab_dfs.append(df)

    def _get_offset_and_df(self, token_id: int):
        i = bisect.bisect_left(self._vocab_ids, token_id)
        if i < len(self._vocab_ids) and self._vocab_ids[i] == token_id:
            return self._vocab_offsets[i], self._vocab_dfs[i]
        return None, 0

    def _read_postings_with_tf_positions(self, token_id: int):
        """Retorna lista de tuples (doc_id, tf, [positions...])."""
        offset, df = self._get_offset_and_df(int(token_id))
        if offset is None:
            return [], 0
        data = self._postings
        pos = offset
        n_docs, pos = decode_varint(data, pos)
        docs = []
        prev = 0
        for _ in range(n_docs):
            delta_doc, pos = decode_varint(data, pos)
            prev += delta_doc
            doc_id = prev
            tf, pos = decode_varint(data, pos)
            positions = []
            prev_pos = 0
            for _ in range(tf):
                pdelta, pos = decode_varint(data, pos)
                prev_pos += pdelta
                positions.append(prev_pos)
            docs.append((doc_id, tf, positions))
        return docs, df

    @staticmethod
    def _idf(N: int, df: int) -> float:
        # BM25-style idf (log form). Prevent negative by adding 0.5 (probabilistic)
        return math.log(1.0 + (N - df + 0.5) / (df + 0.5))

    def search_bm25(self, tokens, limit: int = 5, return_snippet: bool = True):
        """Tokens: iterable of token_ids (int).
           Retorna lista de dicts com: doc_id, score, matched_terms{token:tf}, snippet.
        """
        scores = defaultdict(float)
        tfs_by_doc = defaultdict(lambda: defaultdict(int))
        positions_by_doc = defaultdict(lambda: defaultdict(list))

        # optional stop-word filter by df fraction (keep your existing heuristic)
        idf_threshold = int(self.N * IDF_MAX_FRACTION)

        for token in tokens:
            docs, df = self._read_postings_with_tf_positions(int(token))
            # ignore super-common tokens (if query long)
            if len(tokens) > 2 and df > idf_threshold:
                continue
            idf = self._idf(self.N, df)
            for doc_id, tf, positions in docs:
                # BM25 term contribution
                dl = self._get_doc_length(doc_id)  # implement fast doc-length lookup (see mais abaixo)
                denom = tf + self.k1 * (1 - self.b + self.b * (dl / self.avgdl))
                score = idf * ((tf * (self.k1 + 1)) / denom)
                scores[doc_id] += score
                tfs_by_doc[doc_id][token] += tf
                positions_by_doc[doc_id][token].extend(positions)

        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:limit]
        results = []
        for doc_id, score in ranked:
            res = {"doc_id": doc_id, "score": score, "matched": dict(tfs_by_doc[doc_id])}
            if return_snippet:
                # build snippet from positions (pick earliest match and show window)
                snippet = self._build_snippet(doc_id, positions_by_doc[doc_id])
                res["snippet"] = snippet
            results.append(res)
        return results

    def _get_doc_length(self, doc_id: int) -> int:
        # A simple approach: store doc lengths in meta -> or create doc_lengths.bin.
        # If you added doc_lengths into meta.json (dict) you can fetch quickly.
        # Here: try meta._doc_lengths (populated if builder wrote it), fallback to avgdl.
        dl_map = self._meta.get("doc_lengths")
        if dl_map:
            return int(dl_map.get(str(doc_id), self.avgdl))
        return int(self.avgdl)

    def _build_snippet(self, doc_id: int, positions_by_token: dict):
        # This is a minimal snippet builder: choose smallest position among tokens and extract +/- window tokens.
        # Requires DocumentStore that can return tokenized form or raw text + token offsets.
        # For now we'll return a simple placeholder if no doc store or not token-aligned.
        # You can enhance by storing token->char offsets at index-time.
        return "(snippet not available — implement doc char offsets for real snippets)"

    def close(self):
        try:
            self._postings.close()
        except:
            pass
        try:
            self._pf.close()
        except:
            pass
        try:
            self._doc_store.close()
        except:
            pass

    def __enter__(self) -> "InvertedIndexSearcher":
        return self

    def __exit__(self, *_) -> None:
        self.close()