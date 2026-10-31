# -*- coding: utf-8 -*-
# engine/training/quantize.py
"""
Quantização GGUF via llama-quantize.exe.

Usa o binário provisionado por `engine.tools.provision`. Se não existir,
retorna QuantizeResult(success=False) com instrução clara (OSL-15).

God: Hefesto (transforma F16 em Q4_K_M).
OSL-15: binário ausente não derruba; sugere `orn tools provision`.
"""

from __future__ import annotations

import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path

_VALID_TYPES = {
    "q2_k", "q3_k_s", "q3_k_m", "q3_k_l",
    "q4_0", "q4_1", "q4_k_s", "q4_k_m",
    "q5_0", "q5_1", "q5_k_s", "q5_k_m",
    "q6_k", "q8_0", "f16", "f32",
}


@dataclass
class QuantizeResult:
    success:     bool
    output_path: Path | None = None
    quant_type:  str = ""
    size_mb:     float = 0.0
    elapsed_s:   float = 0.0
    error:       str | None = None


def quantize_gguf(
    input_gguf: Path,
    output_gguf: Path,
    quant_type: str = "q4_k_m",
    *,
    force: bool = False,
    timeout: int = 600,
) -> QuantizeResult:
    t0 = time.monotonic()

    if not input_gguf.exists():
        return QuantizeResult(
            success=False, error=f"input não encontrado: {input_gguf}",
            elapsed_s=round(time.monotonic() - t0, 2),
        )
    qt = quant_type.lower().strip()
    if qt not in _VALID_TYPES:
        return QuantizeResult(
            success=False,
            error=f"quant_type inválido: {qt} (válidos: {sorted(_VALID_TYPES)})",
            elapsed_s=round(time.monotonic() - t0, 2),
        )
    if output_gguf.exists() and not force:
        return QuantizeResult(
            success=False,
            error=f"output já existe: {output_gguf} (use --force para sobrescrever)",
            elapsed_s=round(time.monotonic() - t0, 2),
        )

    # localiza o binário
    from engine.tools.provision import find_tool
    exe = find_tool("llama-quantize")
    if exe is None:
        return QuantizeResult(
            success=False,
            error=(
                "llama-quantize.exe não encontrado. "
                "Rode `orn tools provision` para compilar do source."
            ),
            elapsed_s=round(time.monotonic() - t0, 2),
        )

    output_gguf.parent.mkdir(parents=True, exist_ok=True)
    if output_gguf.exists():
        output_gguf.unlink()

    try:
        proc = subprocess.run(
            [str(exe), str(input_gguf), str(output_gguf), qt.upper()],
            capture_output=True, text=True, timeout=timeout,
            encoding="utf-8", errors="replace",
        )
    except subprocess.TimeoutExpired:
        return QuantizeResult(
            success=False, error=f"timeout {timeout}s",
            elapsed_s=round(time.monotonic() - t0, 2),
        )
    except OSError as exc:
        return QuantizeResult(
            success=False, error=f"execução falhou: {exc}",
            elapsed_s=round(time.monotonic() - t0, 2),
        )

    if proc.returncode != 0:
        tail = (proc.stderr or proc.stdout or "")[-600:]
        return QuantizeResult(
            success=False,
            error=f"llama-quantize rc={proc.returncode}: {tail}",
            elapsed_s=round(time.monotonic() - t0, 2),
        )

    if not output_gguf.exists():
        return QuantizeResult(
            success=False,
            error="llama-quantize retornou 0 mas output não existe",
            elapsed_s=round(time.monotonic() - t0, 2),
        )

    size_mb = round(output_gguf.stat().st_size / (1024 * 1024), 1)
    return QuantizeResult(
        success=True,
        output_path=output_gguf,
        quant_type=qt.upper(),
        size_mb=size_mb,
        elapsed_s=round(time.monotonic() - t0, 2),
    )
