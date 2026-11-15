
# -*- coding: utf-8 -*-
"""Decisão de auto-search + crawler — específico do web (não do bridge)."""
from __future__ import annotations

import sys


def parse_search_decision(text: str) -> str | None:
    if not text:
        return None
    normalized = text.strip().lower()
    for prefix in ("search:", "busca:", "pesquisar:", "buscar:", "pesquisa:"):
        if normalized.startswith(prefix):
            term = text.strip()[len(prefix):].strip()
            if not term or len(term.split()) > 3:
                return None
            return term
    return None


def decide_search(prompt: str, facade) -> str | None:
    if not prompt or not prompt.strip():
        return None
    decision_prompt = (
        "Você é um motor de decisão de busca.\n"
        "Leia a pergunta e decida:\n"
        "- Se precisar de dados externos, fatos específicos ou pesquisa: "
        "responda APENAS com BUSCA:<termo>\n"
        "- Se for conhecimento geral de programação: responda APENAS com NO\n\n"
        "Regras:\n"
        "- BUSCA:<termo> deve ter no máximo 3 palavras\n"
        "- Nenhuma explicação extra\n\n"
        f"Pergunta: {prompt.strip()}"
    )
    try:
        out = facade.ask(decision_prompt, max_tokens=20)
    except Exception:
        return None
    return parse_search_decision(str(out))


def run_crawler(query: str) -> tuple[str, str, str]:
    try:
        from engine.tools.crawler import OrnCrawler
        result = OrnCrawler().search(query, source="auto")
        if result.ok:
            return result.to_prompt_block(), result.source, result.url
    except Exception:
        pass
    return "", "", ""


# ── testes embutidos ─────────────────────────────────────────
def _run_tests() -> int:
    passed = failed = 0

    def _check(name: str, cond: bool, detail: str = "") -> None:
        nonlocal passed, failed
        if cond:
            print(f"  [OK] {name}")
            passed += 1
        else:
            print(f"  [X]  {name}" + (f" — {detail}" if detail else ""))
            failed += 1

    _check("parse: NO → None", parse_search_decision("NO") is None)
    _check("parse: 'search: asyncio' → 'asyncio'",
           parse_search_decision("search: asyncio") == "asyncio")
    _check("parse: 'BUSCA: python 3.13' → 'python 3.13'",
           parse_search_decision("BUSCA: python 3.13") == "python 3.13")
    _check("parse: 4 palavras → None",
           parse_search_decision("search: a b c d") is None)
    _check("parse: vazio → None", parse_search_decision("") is None)

    class _FacadeOk:
        def ask(self, p, max_tokens=20):
            return "search: asyncio"

    class _FacadeFail:
        def ask(self, p, max_tokens=20):
            raise RuntimeError("boom")

    f_ok = _FacadeOk()
    _check("decide: happy path",
           decide_search("como usar asyncio?", f_ok) == "asyncio")
    _check("decide: façade falha → None",
           decide_search("x", _FacadeFail()) is None)
    _check("decide: prompt vazio → None",
           decide_search("", f_ok) is None)

    print()
    if failed == 0:
        print(f"  {passed} teste(s) OK")
        return 0
    print(f"  {passed}/{passed + failed} passaram — {failed} falha(s)")
    return 1


if __name__ == "__main__":
    if "--test" in sys.argv:
        raise SystemExit(_run_tests())
    print("Uso: python -m engine.web.auto_search --test")
    raise SystemExit(1)
