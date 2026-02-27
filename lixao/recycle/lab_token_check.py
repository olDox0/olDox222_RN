# lab_token_check.py
from alfagold.core.transformer import Alfagold
import os

model = Alfagold()
model.load(os.path.expanduser("~/.doxoade/alfagold_v1.pkl"))

chars = ["(", ")", ":", " ", "def", "open"]
print("--- Check de IDs ---")
for c in chars:
    ids = model.tokenizer.encode(c)
    decoded = model.tokenizer.decode(ids)
    print(f"'{c}' -> IDs: {ids} -> Decoded: '{decoded}'")