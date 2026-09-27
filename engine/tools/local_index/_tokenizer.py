# -*- coding: utf-8 -*-
# engine/tools/local_index/_tokenizer.py
"""
ORN — LocalIndex / TokenizerBridge (Hermes Vocabular)
Faz o "pitstop" do tokenizador no pipeline de build do índice.

Filosofia do pitstop:
  O build para um instante, carrega APENAS o vocabulário do modelo
  (vocab_only=True — sem pesos, sem GPU, sem inferência, ~1-2s no N2808),
  e a partir daí todos os documentos passam pelo tokenizador real do Qwen.
  Resultado: tokens no índice invertido são idênticos aos tokens que o LLM
  vai ver durante a busca — sem divergência de vocabulário.

Modos de operação (prioridade decrescente):
  1. Servidor ativo  — envia texto para orn-server tokenizar (zero overhead)
  2. vocab_only      — carrega vocab do GGUF localmente (llama_cpp, ~1-2s)
  3. Fallback hash   — hashing determinístico por palavra (sem deps externas)

OSL-3:  _llm instanciado lazy; liberado por close()
OSL-4:  Cada método faz uma coisa.
OSL-7:  tokenize() NUNCA levanta — retorna lista vazia em falha fatal.
OSL-15: Fallback hash garante que o build nunca aborta por falta do modelo.
OSL-18: Stdlib only neste módulo; llama_cpp importado lazy.
God: Hermes — entrega os tokens antes do indexador acordar.
"""

from __future__ import annotations

import hashlib
import json
import logging
import socket
import struct
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger("engine.tools.local_index.tokenizer")

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

_SERVER_HOST = "127.0.0.1"
_SERVER_PORT = 8371
_SERVER_TIMEOUT = 2.0          # segundos — pitstop não pode travar o build

# Comando especial de tokenização (protocolo ORN TCP)
# O servidor responde {"tokens": [int, ...]} para este payload.
_TOKENIZE_CMD = "TOKENIZE"

# Tamanho máximo de texto por pitstop (chars)
_MAX_TEXT_CHARS = 4096


# ---------------------------------------------------------------------------
# TokenizerBridge
# ---------------------------------------------------------------------------

class TokenizerBridge:
    """Ponte entre o pipeline de indexação e o vocabulário do Qwen.

    Uso típico no build:
        tok = TokenizerBridge()
        tok.pitstop()               # avisa e tenta pré-carregar
        for doc in docs:
            tokens = tok.tokenize(doc.body)
            builder.add_document(doc.id, tokens)
        tok.close()

    Args:
        gguf_path: Caminho explícito para o GGUF. Se None, usa BridgeConfig.
    """

    def __init__(self, gguf_path: str | Path | None = None) -> None:
        self._gguf_path: str | None = str(gguf_path) if gguf_path else None
        self._llm: object | None = None          # Llama(vocab_only=True)
        self._mode: str = "hash"                 # "server" | "vocab" | "hash"
        self._pitstop_done: bool = False
        self._stats = {"tokenized": 0, "fallback": 0, "errors": 0}

    # ------------------------------------------------------------------
    # API pública
    # ------------------------------------------------------------------

    def pitstop(self) -> str:
        """Detecta modo de operação e pré-carrega o que for necessário.

        Retorna o modo escolhido: "server" | "vocab" | "hash".
        Chame uma vez antes do loop principal do build.
        """
        if self._pitstop_done:
            return self._mode

        self._pitstop_done = True

        # Tenta modo servidor primeiro (zero custo de carregamento)
        if self._server_available():
            self._mode = "server"
            logger.info("[PITSTOP] Tokenizador via servidor ORN (porta %d).", _SERVER_PORT)
            return self._mode

        # Tenta vocab_only (sem pesos — rápido)
        gguf = self._resolve_gguf()
        if gguf:
            try:
                self._load_vocab_only(gguf)
                self._mode = "vocab"
                logger.info("[PITSTOP] Tokenizador vocab_only: %s", Path(gguf).name)
                return self._mode
            except Exception as exc:
                logger.warning("[PITSTOP] vocab_only falhou (%s); usando fallback hash.", exc)

        self._mode = "hash"
        logger.warning(
            "[PITSTOP] Tokenizador real indisponível — usando hash deterministico. "
            "Inicie o orn-server ou verifique o modelo GGUF para qualidade máxima."
        )
        return self._mode

    def tokenize(self, text: str) -> list[int]:
        """Tokeniza `text` no modo ativo.

        OSL-7: Nunca levanta — retorna [] em falha fatal.

        Args:
            text: Texto limpo do documento (body após strip_html).

        Returns:
            Lista de token IDs (int) para o InvertedIndexBuilder.
        """
        if not text or not text.strip():
            return []

        # Trunca para evitar pitstop longo em documentos gigantes
        text = text[:_MAX_TEXT_CHARS]

        try:
            if self._mode == "server":
                tokens = self._server_tokenize(text)
                if tokens is not None:
                    self._stats["tokenized"] += 1
                    return tokens
                # Servidor caiu mid-build → degrada para vocab ou hash
                self._mode = "vocab" if self._llm else "hash"

            if self._mode == "vocab" and self._llm is not None:
                tokens = self._vocab_tokenize(text)
                self._stats["tokenized"] += 1
                return tokens

        except Exception as exc:
            self._stats["errors"] += 1
            logger.debug("[PITSTOP] tokenize erro (%s); usando fallback.", exc)

        # Fallback hash
        self._stats["fallback"] += 1
        return self._hash_tokenize(text)

    def close(self) -> None:
        """Libera recursos. Chame ao fim do build."""
        if self._llm is not None:
            try:
                # llama_cpp não tem close() formal — deixa para o GC
                del self._llm
            except Exception:
                pass
            self._llm = None
        logger.debug("[PITSTOP] stats=%s", self._stats)

    def stats(self) -> dict:
        """Retorna contadores de tokenização."""
        return dict(self._stats, mode=self._mode)

    # ------------------------------------------------------------------
    # Detecção e carregamento
    # ------------------------------------------------------------------

    def _server_available(self) -> bool:
        """Verifica se o orn-server está respondendo na porta padrão."""
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(_SERVER_TIMEOUT)
                s.connect((_SERVER_HOST, _SERVER_PORT))
            return True
        except (ConnectionRefusedError, OSError):
            return False

    def _resolve_gguf(self) -> str | None:
        """Retorna caminho do GGUF, seja explícito ou via BridgeConfig."""
        if self._gguf_path:
            p = Path(self._gguf_path)
            return str(p) if p.exists() else None
        try:
            from engine.core.llm_bridge import BridgeConfig  # noqa: PLC0415
            p = BridgeConfig().model_path
            return str(p) if p.exists() else None
        except Exception:
            return None

    def _load_vocab_only(self, gguf: str) -> None:
        """Carrega apenas o vocabulário do GGUF (sem pesos, sem GPU)."""
        from llama_cpp import Llama  # noqa: PLC0415 — lazy (OSL-3)

        self._llm = Llama(
            model_path=gguf,
            n_ctx=0,           # contexto mínimo
            n_gpu_layers=0,    # CPU-only
            vocab_only=True,   # NÃO carrega pesos — só o vocabulário
            verbose=False,
        )

    # ------------------------------------------------------------------
    # Backends de tokenização
    # ------------------------------------------------------------------

    def _server_tokenize(self, text: str) -> list[int] | None:
        """Envia texto ao orn-server para tokenização via protocolo TCP."""
        try:
            payload = (
                json.dumps({"cmd": _TOKENIZE_CMD, "text": text}) + "\n"
            ).encode("utf-8")

            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(_SERVER_TIMEOUT)
                s.connect((_SERVER_HOST, _SERVER_PORT))
                s.settimeout(None)
                s.sendall(payload)

                data = bytearray()
                while True:
                    chunk = s.recv(65536)
                    if not chunk:
                        break
                    data.extend(chunk)
                    if data.endswith(b"\n"):
                        break

            resp = json.loads(data.decode("utf-8").strip())
            tokens = resp.get("tokens")
            if isinstance(tokens, list) and tokens:
                return [int(t) for t in tokens]
            return None

        except Exception:
            return None

    def _vocab_tokenize(self, text: str) -> list[int]:
        """Tokeniza usando o vocab Qwen carregado localmente."""
        raw: list[int] = self._llm.tokenize(  # type: ignore[union-attr]
            text.encode("utf-8", errors="replace"),
            add_bos=False,
            special=False,
        )
        return raw

    @staticmethod
    def _hash_tokenize(text: str) -> list[int]:
        """Fallback: hash MD5 truncado por palavra (determinístico, sem deps).

        OSL-15: Garante que o build nunca aborta por ausência do modelo.
        Os IDs não correspondem ao vocabulário real — qualidade de busca
        inferior, mas o índice é construído sem erros.
        """
        tokens: list[int] = []
        for word in text.lower().split():
            h = struct.unpack(">I", hashlib.md5(word.encode("utf-8", errors="ignore")).digest()[:4])[0]
            tokens.append(h % (2**30))  # cabe em u32 com folga
        return tokens