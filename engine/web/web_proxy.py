# -*- coding: utf-8 -*-
"""Helpers de proxy HTTP->TCP para o servidor de inferência."""

from __future__ import annotations

import json
import socket
from typing import Any


def query_infer_raw(payload: bytes, host: str, infer_port: int) -> dict[str, Any] | None:
    """Envia payload para o SiCDox Server e retorna dict ou None."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(3.0)
            s.connect((host, infer_port))
            s.settimeout(None)
            s.sendall(payload)
            data = b""
            while True:
                chunk = s.recv(1048576)  # 1 MB
                if not chunk:
                    break
                data += chunk
                if data.endswith(b"\n"):
                    break
        return json.loads(data.decode("utf-8").strip())
    except Exception:
        return None


def parse_search_decision(text: str) -> str | None:
    """Parse defensivo da resposta de decisão."""
    if not text:
        return None
    normalized = text.strip().lower()
    for prefix in ("search:", "busca:", "pesquisar:", "buscar:", "pesquisa:"):
        if normalized.startswith(prefix):
            term = text.strip()[len(prefix):].strip()
            if not term or len(term.split()) > 5:
                return None
            return term
    return None


def decide_search(prompt: str, host: str, infer_port: int) -> str | None:
    """1ª pass: pergunta ao modelo se precisa de busca externa."""
    decision_prompt = (
        "Você é um motor de decisão de busca.\n"
        "Leia a pergunta e decida:\n"
        "- Se precisar de dados externos, fatos específicos ou pesquisa: responda APENAS com BUSCA:<termo>\n"
        "- Se for conhecimento geral de programação: responda APENAS com NO\n\n"
        "Regras:\n"
        "- BUSCA:<termo> deve ter no máximo 3 palavras\n"
        "- Nenhuma explicação extra\n\n"
        f"Pergunta: {prompt.strip()}"
    )
    resp = query_infer_raw(
        (json.dumps({"prompt": decision_prompt, "max_tokens": 20}) + "\n").encode(),
        host=host,
        infer_port=infer_port,
    )
    if not resp or resp.get("error"):
        return None
    return parse_search_decision(str(resp.get("output", "")))


def run_crawler(query: str) -> tuple[str, str, str]:
    """Executa o crawler e retorna (context_block, source, source_url)."""
    try:
        from engine.tools.crawler import OrnCrawler  # noqa: PLC0415

        result = OrnCrawler().search(query, source="auto")
        if result.ok:
            return result.to_prompt_block(), result.source, result.url
    except Exception:
        pass
    return "", "", ""
