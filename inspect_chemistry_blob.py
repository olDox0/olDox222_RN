# inspect_chemistry_blob.py
import sqlite3, array, os, sys, textwrap, binascii
from engine.tools.local_index import _decompress, TokenizerBridge

DB = "data/index/wikipedia_en_chemistry_mini_2026_01.db"
TITLE = "chemistry"

def hexdump(b: bytes, n: int = 128):
    return binascii.hexlify(b[:n]).decode("ascii")

def main():
    print("DB:", DB)
    if not os.path.exists(DB):
        print("ERROR: DB not found:", DB); sys.exit(1)

    con = sqlite3.connect(DB)
    cur = con.cursor()
    cur.execute("SELECT p.id, p.title, c.token_blob, LENGTH(c.token_blob) FROM pages p JOIN content_pool c ON p.content_hash = c.hash WHERE LOWER(p.title)=? LIMIT 1", (TITLE,))
    row = cur.fetchone()
    if not row:
        print("No row for title:", TITLE); sys.exit(0)
    doc_id, title, blob, blob_len = row
    print("doc_id:", doc_id, "title:", title, "blob_len:", blob_len)

    if not blob:
        print("Blob empty; nothing to do"); sys.exit(0)

    # raw bytes preview
    print("\n-- raw blob preview (hex, first 256 bytes) --")
    try:
        print(hexdump(blob, 256))
    except Exception as e:
        print("hex preview error:", e)

    # try decompress
    try:
        decompressed = _decompress(blob)
        print("\n_decompress OK, len:", len(decompressed))
    except Exception as e:
        print("\n_decompress FAILED:", e)
        # dump a bit of the raw blob for inspection and exit
        con.close()
        sys.exit(0)

    # if decompressed is bytes, try interpret as token-array (array of int32)
    if len(decompressed) % 4 == 0:
        try:
            arr = array.array("i")
            arr.frombytes(decompressed)
            toks = arr.tolist()
            print("tokens count:", len(toks))
            if toks:
                print("tokens sample (first 20):", toks[:20])
                print("token min/max:", min(toks), max(toks))
        except Exception as e:
            print("token array decode failed:", e)
    else:
        print("decompressed length not multiple of 4 -> likely not token-array. len =", len(decompressed))
        # try decode as utf-8 text fallback
        try:
            txt = decompressed.decode("utf-8", errors="replace")
            print("\n-- fallback decoded text (first 2000 chars) --\n")
            print(txt[:2000])
        except Exception as e:
            print("fallback decode failed:", e)

    # try detokenize using TokenizerBridge.bytes_to_text
    try:
        text = TokenizerBridge.bytes_to_text(decompressed)
        print("\nTokenizerBridge.bytes_to_text output length:", len(text))
        print("\n-- detokenized preview (first 2000 chars) --\n")
        print(text[:2000])
    except Exception as e:
        print("TokenizerBridge.bytes_to_text FAILED:", e)
        # If tokens existed, check for tokens outside vocab range
        try:
            vocab = TokenizerBridge.get_vocab()
            print("vocab n_vocab (if available):", getattr(vocab, "n_vocab", lambda: "unknown")())
        except Exception as e2:
            print("Could not load vocab:", e2)

    con.close()
    print("\nDone.")

if __name__ == '__main__':
    main()