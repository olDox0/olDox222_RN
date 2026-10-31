# -*- coding: utf-8 -*-
# merge_lora_numpy_gguf.py
"""
🐺 ORN SOVEREIGN GGUF MERGER (Zero PyTorch, Zero Transformers)
Funde adaptadores PEFT LoRA diretamente no arquivo GGUF F16 via NumPy puro.
Compatível com SSE4.2 (Celeron N2808) e qualquer ambiente restrito.
"""
# [DOXOADE:VULCAN]
# [VULCAN-SKIP] Proteção contra introspecção Click
import os, sys; _b = os.path.join(os.getcwd(), ".doxoade", "vulcan", "bootstrap.py")
if os.path.exists(_b):
    import importlib.util as _u; _s = _u.spec_from_file_location("_vb", _b)
    _m = _u.module_from_spec(_s); _s.loader.exec_module(_m); _m.ignite(__file__, globals())
# [/DOXOADE:VULCAN]
import sys
import json
import shutil
import struct
import time
from pathlib import Path

# Injeta o leitor nativo do llama.cpp (puramente NumPy, sem torch)
sys.path.insert(0, str(Path("thirdparty/llama.cpp/gguf-py")))
try:
    import gguf
except ImportError:
    print("❌ Falha ao carregar 'gguf' de thirdparty/llama.cpp/gguf-py")
    sys.exit(1)

import numpy as np

# Caminhos
BASE_GGUF = Path("models/smolm_sys/SmolLM2-135M-Instruct-f16.gguf")
ADAPTER_DIR = Path("data/training/lora_adapter_peft_upper6_200")
OUTPUT_GGUF = Path("models/smolm_sys/Brunnr-135M-Instruct-f16.gguf")


def read_safetensors_pure(path: Path) -> dict[str, np.ndarray]:
    """Lê tensores de um .safetensors sem depender de nenhuma biblioteca externa."""
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


def main():
    print("=" * 75)
    print("🐺 ORN SOVEREIGN GGUF MERGER — FUSÃO MATRICIAL PURA (NUMPY)")
    print(f"   Base:    {BASE_GGUF}")
    print(f"   Adapter: {ADAPTER_DIR}")
    print(f"   Destino: {OUTPUT_GGUF}")
    print("=" * 75)

    if not BASE_GGUF.exists():
        print(f"❌ Modelo base não encontrado: {BASE_GGUF}")
        return
    if not (ADAPTER_DIR / "adapter_model.safetensors").exists():
        print(f"❌ Adaptador não encontrado: {ADAPTER_DIR / 'adapter_model.safetensors'}")
        return

    t0 = time.perf_counter()

    # 1. Carrega hiperparâmetros de escala do LoRA
    with open(ADAPTER_DIR / "adapter_config.json", "r", encoding="utf-8") as f:
        cfg = json.load(f)
    r = cfg.get("r", 8)
    alpha = cfg.get("lora_alpha", 16)
    scale = alpha / r
    print(f"\n[1/5] Configuração LoRA: r={r}, alpha={alpha} ➔ Escala={scale:.2f}")

    # 2. Carrega pesos do LoRA via parser binário
    print("[2/5] Carregando matrizes A e B do safetensors via NumPy...")
    lora_tensors = read_safetensors_pure(ADAPTER_DIR / "adapter_model.safetensors")
    print(f"   ✔ {len(lora_tensors)} matrizes LoRA carregadas na memória.")

    # 3. Lê offsets e metadados do arquivo GGUF
    print("[3/5] Mapeando tensores F16 do arquivo GGUF...")
    reader = gguf.GGUFReader(str(BASE_GGUF))
    gguf_tensor_map = {t.name: t for t in reader.tensors}

    # 4. Clona o arquivo base para o arquivo final
    print(f"[4/5] Clonando modelo base para {OUTPUT_GGUF.name} ({BASE_GGUF.stat().st_size / (1024*1024):.1f} MB)...")
    OUTPUT_GGUF.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(BASE_GGUF, OUTPUT_GGUF)

    # 5. Aplica a fusão matricial diretamente nos offsets dos tensores F16
    print("[5/5] Fundindo tensores adaptados diretamente no GGUF...")

    PROJ_MAP = {
        "q_proj": "attn_q.weight",
        "k_proj": "attn_k.weight",
        "v_proj": "attn_v.weight",
        "o_proj": "attn_output.weight",
    }

    fused_count = 0
    with open(OUTPUT_GGUF, "r+b") as f_out:
        for key_b, mat_b in lora_tensors.items():
            if not key_b.endswith(".lora_B.weight"):
                continue

            key_a = key_b.replace(".lora_B.weight", ".lora_A.weight")
            if key_a not in lora_tensors:
                continue

            mat_a = lora_tensors[key_a]

            # Identifica camada e projeção
            # Exemplo: base_model.model.model.layers.6.self_attn.q_proj.lora_B.weight
            parts = key_b.split(".")
            layer_idx = None
            proj_name = None
            for idx, p in enumerate(parts):
                if p == "layers" and idx + 1 < len(parts):
                    layer_idx = parts[idx + 1]
                if p in PROJ_MAP:
                    proj_name = p

            if not layer_idx or not proj_name:
                continue

            gguf_name = f"blk.{layer_idx}.{PROJ_MAP[proj_name]}"
            if gguf_name not in gguf_tensor_map:
                print(f"   ⚠ Tensor GGUF correspondente não encontrado: {gguf_name}")
                continue

            target_tensor = gguf_tensor_map[gguf_name]

            # Cálculo de Silício: dW = scale * (B x A)
            delta_w = (scale * (mat_b.astype(np.float32) @ mat_a.astype(np.float32)))

            # Lê os pesos originais F16 do arquivo clonado para validação
            abs_offset = getattr(target_tensor, "data_offset", None) or (reader.data_offset + getattr(target_tensor, "offset", 0))
            f_out.seek(abs_offset)
            original_bytes = f_out.read(target_tensor.n_bytes)
            orig_mat = np.frombuffer(original_bytes, dtype=np.float16).reshape(target_tensor.data.shape)

            # Convenção ggml: tensores lineares são [in, out] (transpostos em relação ao HF)
            expected = delta_w.T
            if orig_mat.shape != expected.shape:
                if orig_mat.shape == delta_w.shape:
                    expected = delta_w
                    print(f"   ⚠ layout HF direto (nao-transposto) em {gguf_name}")
                else:
                    raise RuntimeError(f"FATAL {gguf_name}: {orig_mat.shape} != {expected.shape}")
            
            # Soma com clip para evitar estouro de f16 (±65504)
            merged = np.clip(orig_mat.astype(np.float32) + expected, -65504.0, 65504.0)

            # Grava o tensor fundido de volta exatamente nos mesmos bytes
            f_out.seek(abs_offset)
            f_out.write(merged.astype(np.float16).tobytes())
            fused_count += 1
            print(f"   ✔ Fundido: {gguf_name:<28} │ ΔW Shape: {delta_w.shape}")

    elapsed = time.perf_counter() - t0
    print("\n" + "═" * 75)
    print(f"🏁 SUCESSO TOTAL! {fused_count} tensores fundidos em {elapsed:.2f}s!")
    print(f"📁 Modelo final pronto para C puro: {OUTPUT_GGUF.resolve()}")
    print("═" * 75)


if __name__ == "__main__":
    main()
