# -*- coding: utf-8 -*-
# engine/tools/inverted_index.py

from __future__ import annotations

import json
import struct
from collections import defaultdict
from pathlib import Path


# ------------------------------------------------
# VARINT (compressão leve)
# ------------------------------------------------

def encode_varint(n: int) -> bytes:
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


def decode_varint(data: bytes, pos: int):
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


# ------------------------------------------------
# BUILDER
# ------------------------------------------------

class InvertedIndexBuilder:

    def __init__(self):
        self.postings = defaultdict(list)
        self.doc_count = 0

    def add_document(self, doc_id: int, tokens):

        seen = set()

        for t in tokens:

            if t in seen:
                continue

            seen.add(t)
            self.postings[t].append(doc_id)

        self.doc_count = max(self.doc_count, doc_id)

    def finalize(self):

        for token in self.postings:

            self.postings[token].sort()

    def write(self, path: Path):

        path.mkdir(parents=True, exist_ok=True)

        vocab = {}
        postings_bytes = bytearray()

        for token, docs in sorted(self.postings.items()):

            vocab[token] = len(postings_bytes)

            last = 0

            for doc in docs:

                delta = doc - last
                postings_bytes += encode_varint(delta)
                last = doc

            postings_bytes += encode_varint(0)

        with open(path / "postings.bin", "wb") as f:
            f.write(postings_bytes)

        with open(path / "vocab.json", "w") as f:
            json.dump(vocab, f)

        with open(path / "meta.json", "w") as f:
            json.dump({"doc_count": self.doc_count}, f)


# ------------------------------------------------
# SEARCHER
# ------------------------------------------------

class InvertedIndexSearcher:

    def __init__(self, path: Path):

        with open(path / "vocab.json") as f:
            self.vocab = json.load(f)

        with open(path / "postings.bin", "rb") as f:
            self.postings = f.read()

        with open(path / "meta.json") as f:
            self.meta = json.load(f)

    def _read_postings(self, token):

        token = str(token)

        if token not in self.vocab:
            return []

        pos = self.vocab[token]
        data = self.postings

        docs = []
        last = 0

        while True:

            delta, pos = decode_varint(data, pos)

            if delta == 0:
                break

            last += delta
            docs.append(last)

        return docs

    def search(self, tokens, limit=5):

        scores = defaultdict(int)

        for token in tokens:

            docs = self._read_postings(token)

            for d in docs:

                scores[d] += 1

        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)

        return [doc for doc, _ in ranked[:limit]]