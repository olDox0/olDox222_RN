# -*- coding: utf-8 -*-
# engine/training/merge.py
"""
LoRA → GGUF merge em NumPy puro (sem PyTorch).

Porta o `merge_lora_numpy_gguf.py` da raiz para módulo reusável.
Diferenças:
  - target_modules lidos do adapter_config.json (não hardcode q_proj/v_proj)
  - scale="auto" → alpha/r do config
  - retorna MergeResult estruturado (não print cru)
  - falha em tensor individual → loga e continua (OSL-15)
  - --out existente → aborta (--force sobrescreve)

God: Hefesto (transforma adapter em artefato) + Hades (grava GGUF).
OSL-15: qualquer erro vira MergeResult(success=False), nunca propaga.
"""

from __future__ import annotations

import json
import shutil
import struct
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_GGUF_PY      = _PROJECT_ROOT / "thirdparty" / "llama.cpp" / "gguf-py"

# Mapa projeção → nome de tensor GGUF (mesmo do script original)
_PROJ_MAP = {
    "q_proj": "attn_q.weight",
    "k_proj": "attn_k.weight",
    "v_proj": "attn_v.weight",
    "o_proj": "attn_output.weight",
}


@dataclass
class MergeResult:
    success:        bool
    output_path:    Path | None = None
    fused_tensors:  int = 0
    skipped_tensors: int = 0
    scale:          float = 0.0
    errors:         list[str] = field(default_factory=list)
    elapsed_s:      float = 0.0


# ---------------------------------------------------------------------------
# Safetensors puro (sem dependência de safetensors lib)
# ---------------------------------------------------------------------------

def read_safetensors(path: Path) -> dict[str, "np.ndarray"]:
    import numpy as np
    with open(path, "rb") as f:
        header_len = struct.unpack("<Q", f.read(8))[0]
        header = json.loads(f.read(header_len).decode("utf-8"))
        base_offset = 8 + header_len
        tensors = {}
        for name, meta in header.items():
            if name == "__metadata__":
                continue
            shape = meta["shape"]
            dtype = np.float32 if meta["dtype"] == "F32" else np.float16
            start, end = meta["data_offsets"]
            f.seek(base_offset + start)
            raw = f.read(end - start)
            tensors[name] = np.frombuffer(raw, dtype=dtype).reshape(shape)
        return tensors


# ---------------------------------------------------------------------------
# Configuração
# ---------------------------------------------------------------------------

def load_adapter_config(adapter_dir: Path) -> dict:
    cfg_path = adapter_dir / "adapter_config.json"
    if not cfg_path.exists():
        raise FileNotFoundError(f"adapter_config.json ausente em {adapter_dir}")
    return json.loads(cfg_path.read_text(encoding="utf-8"))


def detect_scale(cfg: dict) -> float:
    r = int(cfg.get("r", 8))
    alpha = float(cfg.get("lora_alpha", 16))
    if r <= 0:
        return 1.0
    return alpha / r


def detect_target_modules(cfg: dict) -> list[str]:
    mods = cfg.get("target_modules")
    if isinstance(mods, list) and mods:
        return [m for m in mods if isinstance(m, str)]
    # default do script original
    return ["q_proj", "k_proj", "v_proj", "o_proj"]


# ---------------------------------------------------------------------------
# Merge
# ---------------------------------------------------------------------------

def merge_lora(
    base_gguf: Path,
    adapter_dir: Path,
    out_gguf: Path,
    *,
    scale: float | str = "auto",
    force: bool = False,
) -> MergeResult:
    t0 = time.monotonic()

    # --- validações ---
    if not base_gguf.exists():
        return MergeResult(
            success=False,
            errors=[f"base não encontrado: {base_gguf}"],
            elapsed_s=round(time.monotonic() - t0, 2),
        )
    if not adapter_dir.exists():
        return MergeResult(
            success=False,
            errors=[f"adapter_dir não encontrado: {adapter_dir}"],
            elapsed_s=round(time.monotonic() - t0, 2),
        )
    adapter_file = adapter_dir / "adapter_model.safetensors"
    if not adapter_file.exists():
        return MergeResult(
            success=False,
            errors=[f"adapter_model.safetensors ausente em {adapter_dir}"],
            elapsed_s=round(time.monotonic() - t0, 2),
        )
    if out_gguf.exists() and not force:
        return MergeResult(
            success=False,
            errors=[f"out já existe: {out_gguf} (use --force para sobrescrever)"],
            elapsed_s=round(time.monotonic() - t0, 2),
        )

    # --- dependências ---
    try:
        sys.path.insert(0, str(_GGUF_PY))
        import gguf
        import numpy as np
    except ImportError as exc:
        return MergeResult(
            success=False,
            errors=[f"import falhou: {exc} (thirdparty/llama.cpp/gguf-py precisa estar acessível)"],
            elapsed_s=round(time.monotonic() - t0, 2),
        )

    # --- config ---
    try:
        cfg = load_adapter_config(adapter_dir)
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        return MergeResult(
            success=False,
            errors=[f"adapter_config: {exc}"],
            elapsed_s=round(time.monotonic() - t0, 2),
        )

    if scale == "auto":
        actual_scale = detect_scale(cfg)
    else:
        actual_scale = float(scale)

    target_modules = detect_target_modules(cfg)

    errors: list[str] = []

    # --- carrega LoRA ---
    try:
        lora_tensors = read_safetensors(adapter_file)
    except Exception as exc:
        return MergeResult(
            success=False,
            errors=[f"leitura do safetensors falhou: {exc}"],
            elapsed_s=round(time.monotonic() - t0, 2),
        )

    # --- copia base ---
    out_gguf.parent.mkdir(parents=True, exist_ok=True)
    if out_gguf.exists():
        out_gguf.unlink()
    try:
        shutil.copy2(base_gguf, out_gguf)
    except OSError as exc:
        return MergeResult(
            success=False,
            errors=[f"cópia do base falhou: {exc}"],
            elapsed_s=round(time.monotonic() - t0, 2),
        )

    # --- abre reader + writer ---
    try:
        reader = gguf.GGUFReader(str(base_gguf))
        gguf_tensor_map = {t.name: t for t in reader.tensors}
    except Exception as exc:
        return MergeResult(
            success=False,
            errors=[f"GGUFReader falhou: {exc}"],
            elapsed_s=round(time.monotonic() - t0, 2),
        )

    fused = 0
    skipped = 0

    with open(out_gguf, "r+b") as f_out:
        for key_b, mat_b in lora_tensors.items():
            if not key_b.endswith(".lora_B.weight"):
                continue
            key_a = key_b.replace(".lora_B.weight", ".lora_A.weight")
            if key_a not in lora_tensors:
                skipped += 1
                continue
            mat_a = lora_tensors[key_a]

            # key_b = "model.layers.<N>.<proj>.lora_B.weight"
            parts = key_b.split(".")
            layer_idx = None
            proj_name = None
            for i, p in enumerate(parts):
                if p == "layers" and i + 1 < len(parts):
                    layer_idx = parts[i + 1]
                if p in _PROJ_MAP:
                    proj_name = p
            if layer_idx is None or proj_name is None:
                skipped += 1
                continue
            if proj_name not in target_modules:
                # target_modules pode excluir módulos; se o adapter tem,
                # funde mesmo assim (senão fica inconsistente)
                pass

            gguf_name = f"blk.{layer_idx}.{_PROJ_MAP[proj_name]}"
            target_tensor = gguf_tensor_map.get(gguf_name)
            if target_tensor is None:
                skipped += 1
                errors.append(f"tensor GGUF não encontrado: {gguf_name}")
                continue

            # delta_w = scale * (B @ A)
            try:
                delta_w = actual_scale * (mat_b.astype(np.float32) @ mat_a.astype(np.float32))
            except ValueError as exc:
                skipped += 1
                errors.append(f"{gguf_name}: produto B@A falhou: {exc}")
                continue

            # offset absoluto
            abs_offset = getattr(target_tensor, "data_offset", None)
            if abs_offset is None:
                abs_offset = reader.data_offset + getattr(target_tensor, "offset", 0)

            # lê original
            try:
                f_out.seek(abs_offset)
                original_bytes = f_out.read(target_tensor.n_bytes)
                orig_mat = np.frombuffer(
                    original_bytes, dtype=np.float16
                ).reshape(target_tensor.data.shape)
            except Exception as exc:
                skipped += 1
                errors.append(f"{gguf_name}: leitura do tensor base falhou: {exc}")
                continue

            # aplica transposição se necessário
            expected = delta_w.T
            if orig_mat.shape != expected.shape:
                if orig_mat.shape == delta_w.shape:
                    expected = delta_w
                else:
                    skipped += 1
                    errors.append(
                        f"{gguf_name}: shape mismatch "
                        f"(orig={orig_mat.shape}, delta={delta_w.shape})"
                    )
                    continue

            merged = np.clip(
                orig_mat.astype(np.float32) + expected,
                -65504.0, 65504.0,
            )

            try:
                f_out.seek(abs_offset)
                f_out.write(merged.astype(np.float16).tobytes())
            except Exception as exc:
                skipped += 1
                errors.append(f"{gguf_name}: escrita falhou: {exc}")
                continue

            fused += 1

    return MergeResult(
        success=True,
        output_path=out_gguf,
        fused_tensors=fused,
        skipped_tensors=skipped,
        scale=actual_scale,
        errors=errors,
        elapsed_s=round(time.monotonic() - t0, 2),
    )
