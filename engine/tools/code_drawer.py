from __future__ import annotations

import json
import os
import re

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _default_store() -> Path:
    env = os.environ.get("ORN_CODE_DRAWER_PATH", "").strip()
    if env:
        return Path(env)
    return Path("data") / "code_drawer.json"


@dataclass
class DrawerSnippet:
    name: str
    lang: str
    inputs: list[str]
    outputs: list[str]
    code: str
    tags: list[str]
    created_at: str
    updated_at: str


class CodeDrawer:
    """Armazena snippets reaproveitáveis e monta código por função + I/O."""

    def __init__(self, store_path: str | Path | None = None) -> None:
        self.store_path = Path(store_path) if store_path else _default_store()

    def _load(self) -> dict[str, Any]:
        if not self.store_path.exists():
            return {"version": 1, "snippets": []}
        try:
            data = json.loads(self.store_path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                return {"version": 1, "snippets": []}
            if "snippets" not in data or not isinstance(data["snippets"], list):
                data["snippets"] = []
            data.setdefault("version", 1)
            return data
        except (json.JSONDecodeError, OSError):
            return {"version": 1, "snippets": []}

    def _save(self, data: dict[str, Any]) -> None:
        self.store_path.parent.mkdir(parents=True, exist_ok=True)
        self.store_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def list_snippets(self, lang: str | None = None) -> list[DrawerSnippet]:
        data = self._load()
        out: list[DrawerSnippet] = []
        for raw in data.get("snippets", []):
            if lang and str(raw.get("lang", "")).lower() != lang.lower():
                continue
            out.append(
                DrawerSnippet(
                    name=str(raw.get("name", "")),
                    lang=str(raw.get("lang", "")),
                    inputs=list(raw.get("inputs", [])),
                    outputs=list(raw.get("outputs", [])),
                    code=str(raw.get("code", "")),
                    tags=list(raw.get("tags", [])),
                    created_at=str(raw.get("created_at", "")),
                    updated_at=str(raw.get("updated_at", "")),
                )
            )
        return out

    def upsert_snippet(
        self,
        *,
        name: str,
        lang: str,
        inputs: list[str],
        outputs: list[str],
        code: str,
        tags: list[str] | None = None,
    ) -> DrawerSnippet:
        clean_name = name.strip()
        clean_lang = lang.strip().lower()
        if not clean_name:
            raise ValueError("name vazio")
        if not clean_lang:
            raise ValueError("lang vazio")
        if not code.strip():
            raise ValueError("code vazio")

        now = _utc_now_iso()
        data = self._load()
        snippets = data["snippets"]

        for row in snippets:
            if row.get("name", "").strip() == clean_name and row.get("lang", "").strip().lower() == clean_lang:
                row["inputs"] = [x.strip() for x in inputs if x.strip()]
                row["outputs"] = [x.strip() for x in outputs if x.strip()]
                row["code"] = code.rstrip() + "\n"
                row["tags"] = [x.strip() for x in (tags or []) if x.strip()]
                row["updated_at"] = now
                self._save(data)
                return DrawerSnippet(
                    name=row["name"],
                    lang=row["lang"],
                    inputs=row["inputs"],
                    outputs=row["outputs"],
                    code=row["code"],
                    tags=row["tags"],
                    created_at=row.get("created_at", now),
                    updated_at=row["updated_at"],
                )

        created = DrawerSnippet(
            name=clean_name,
            lang=clean_lang,
            inputs=[x.strip() for x in inputs if x.strip()],
            outputs=[x.strip() for x in outputs if x.strip()],
            code=code.rstrip() + "\n",
            tags=[x.strip() for x in (tags or []) if x.strip()],
            created_at=now,
            updated_at=now,
        )
        snippets.append(asdict(created))
        self._save(data)
        return created

    def get(self, *, name: str, lang: str | None = None) -> DrawerSnippet | None:
        for sn in self.list_snippets(lang=lang):
            if sn.name == name:
                return sn
        return None

    def assemble(
        self,
        *,
        name: str,
        lang: str,
        inputs: list[str] | None = None,
        outputs: list[str] | None = None,
    ) -> DrawerSnippet | None:
        candidates = self.list_snippets(lang=lang)
        if not candidates:
            return None

        req_in = {x.strip().lower() for x in (inputs or []) if x.strip()}
        req_out = {x.strip().lower() for x in (outputs or []) if x.strip()}

        best: tuple[int, DrawerSnippet] | None = None
        for sn in candidates:
            score = 0
            if sn.name == name:
                score += 6
            if sn.lang.lower() == lang.lower():
                score += 3
            sn_in = {x.strip().lower() for x in sn.inputs}
            sn_out = {x.strip().lower() for x in sn.outputs}
            score += len(req_in & sn_in) * 2
            score += len(req_out & sn_out) * 3
            if req_in and req_in.issubset(sn_in):
                score += 2
            if req_out and req_out.issubset(sn_out):
                score += 2
            if best is None or score > best[0]:
                best = (score, sn)

        if best is None or best[0] <= 0:
            return None
        return best[1]

    @staticmethod
    def extract_code_blocks(text: str) -> list[str]:
        pattern = re.compile(r"\[code-begin\](.*?)\[code-end\]", re.IGNORECASE | re.DOTALL)
        blocks = [m.group(1).strip() for m in pattern.finditer(text or "")]
        return [b for b in blocks if b]

    def save_from_context(
        self,
        *,
        name: str,
        lang: str,
        context: str,
        inputs: list[str] | None = None,
        outputs: list[str] | None = None,
        tags: list[str] | None = None,
    ) -> int:
        blocks = self.extract_code_blocks(context)
        saved = 0
        for i, code in enumerate(blocks, start=1):
            snippet_name = name if i == 1 else f"{name}_{i}"
            self.upsert_snippet(
                name=snippet_name,
                lang=lang,
                inputs=list(inputs or []),
                outputs=list(outputs or []),
                code=code,
                tags=list(tags or []),
            )
            saved += 1
        return saved
