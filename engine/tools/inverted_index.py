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
import struct
from collections import defaultdict
from pathlib import Path

# Tokens presentes em mais de IDF_MAX_FRACTION dos documentos são stop words.
IDF_MAX_FRACTION: float = 0.40

# Formato do vocab binário: (token_id u32, byte_offset u64) = 12 bytes por entrada.
_VOCAB_ENTRY_FMT  = "<IQ"
_VOCAB_ENTRY_SIZE = struct.calcsize(_VOCAB_ENTRY_FMT)   # 12


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
    """Constrói o índice a partir de documentos tokenizados.

    Uso:
        builder = InvertedIndexBuilder()
        for doc_id, tokens in docs:
            builder.add_document(doc_id, tokens)
        builder.finalize()
        builder.write(Path("data/index/source_id"))
    """

    def __init__(self) -> None:
        self.postings:  dict[int, list[int]] = defaultdict(list)
        self.doc_count: int = 0

    def add_document(self, doc_id: int, tokens) -> None:
        """Adiciona documento. tokens é iterável de int (array.array('i'))."""
        seen: set[int] = set()
        for t in tokens:
            t = int(t)
            if t in seen:
                continue
            seen.add(t)
            self.postings[t].append(doc_id)
        self.doc_count = max(self.doc_count, doc_id)

    def finalize(self) -> None:
        """Ordena as posting lists. Chamar antes de write()."""
        for token in self.postings:
            self.postings[token].sort()

    def write(self, path: Path) -> None:
        """Serializa índice em path/.

        Escreve postings.bin, vocab.bin, meta.json.
        """
        path.mkdir(parents=True, exist_ok=True)

        vocab_entries: list[tuple[int, int]] = []
        postings_buf = bytearray()

        for token_id, docs in sorted(self.postings.items()):
            offset = len(postings_buf)
            vocab_entries.append((int(token_id), offset))

            # length-prefix + delta varint
            postings_buf += encode_varint(len(docs))
            prev = 0
            for doc in docs:
                postings_buf += encode_varint(doc - prev)
                prev = doc

        with open(path / "postings.bin", "wb") as f:
            f.write(postings_buf)

        # vocab.bin — pares (u32 token_id, u64 byte_offset), ordenados
        with open(path / "vocab.bin", "wb") as f:
            for token_id, offset in vocab_entries:
                f.write(struct.pack(_VOCAB_ENTRY_FMT, token_id, offset))

        with open(path / "meta.json", "w", encoding="utf-8") as f:
            json.dump({"doc_count": self.doc_count, "fmt": 2}, f)


# ---------------------------------------------------------------------------
# Searcher
# ---------------------------------------------------------------------------

class InvertedIndexSearcher:
    """Busca no índice. Compatível com fmt=1 (vocab.json) e fmt=2 (vocab.bin)."""

    def __init__(self, path: Path) -> None:
        with open(path / "meta.json", encoding="utf-8") as f:
            self._meta = json.load(f)

        fmt = self._meta.get("fmt", 1)
        if fmt >= 2 and (path / "vocab.bin").exists():
            self._load_vocab_binary(path / "vocab.bin")
        else:
            self._load_vocab_json(path / "vocab.json")
            self._legacy = True

        # mmap: acesso lazy ao arquivo de postings
        self._pf = open(path / "postings.bin", "rb")
        self._postings = mmap.mmap(self._pf.fileno(), 0, access=mmap.ACCESS_READ)
        self._legacy = fmt < 2

    def _load_vocab_binary(self, vocab_path: Path) -> None:
        raw = vocab_path.read_bytes()
        n = len(raw) // _VOCAB_ENTRY_SIZE
        self._vocab_ids:     list[int] = []
        self._vocab_offsets: list[int] = []
        for i in range(n):
            tid, off = struct.unpack_from(_VOCAB_ENTRY_FMT, raw, i * _VOCAB_ENTRY_SIZE)
            self._vocab_ids.append(tid)
            self._vocab_offsets.append(off)

    def _load_vocab_json(self, vocab_path: Path) -> None:
        """Carrega vocab.json legado, converte keys para int."""
        with open(vocab_path, encoding="utf-8") as f:
            raw = json.load(f)
        items = sorted((int(k), v) for k, v in raw.items())
        self._vocab_ids     = [k for k, _ in items]
        self._vocab_offsets = [v for _, v in items]

    def _get_offset(self, token_id: int) -> int | None:
        i = bisect.bisect_left(self._vocab_ids, token_id)
        if i < len(self._vocab_ids) and self._vocab_ids[i] == token_id:
            return self._vocab_offsets[i]
        return None

    def _read_postings(self, token_id: int) -> list[int]:
        offset = self._get_offset(token_id)
        if offset is None:
            return []
        data = self._postings
        pos  = offset
        if self._legacy:
            # fmt=1: sentinel-0 termina a lista
            docs: list[int] = []
            prev = 0
            while True:
                delta, pos = decode_varint(data, pos)
                if delta == 0:
                    break
                prev += delta
                docs.append(prev)
            return docs
        else:
            # fmt=2: length-prefix
            n_docs, pos = decode_varint(data, pos)
            docs = []
            prev = 0
            for _ in range(n_docs):
                delta, pos = decode_varint(data, pos)
                prev += delta
                docs.append(prev)
            return docs

    def search(self, tokens, limit: int = 5) -> list[int]:
        """Retorna até limit doc_ids por score de relevância.

        Tokens em >IDF_MAX_FRACTION dos documentos são ignorados (stop words).
        """
        doc_count = max(1, self._meta.get("doc_count", 1))
        idf_threshold = int(doc_count * IDF_MAX_FRACTION)
        scores: dict[int, int] = defaultdict(int)

        for token in tokens:
            docs = self._read_postings(int(token))
            if len(docs) > idf_threshold:
                continue   # stop word implícita
            for d in docs:
                scores[d] += 1

        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        return [doc for doc, _ in ranked[:limit]]

    def close(self) -> None:
        """Libera mmap e file handle."""
        try:
            self._postings.close()
        except Exception:
            pass
        try:
            self._pf.close()
        except Exception:
            pass

    def __enter__(self) -> "InvertedIndexSearcher":
        return self

    def __exit__(self, *_) -> None:
        self.close()