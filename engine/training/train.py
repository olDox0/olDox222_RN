# -*- coding: utf-8 -*-
# engine/training/train.py
"""
LoRA trainer — treina adapter PEFT sobre SmolLM2-135M-Instruct em CPU.

Diferenças vs script original (`brunnr_lora_turbo`):
  - target_modules completos (q/k/v/o) em vez de só q/v
  - aplica `tokenizer.apply_chat_template()` (não texto cru)
  - eval_strategy + val.jsonl + EarlyStopping
  - carrega de data/processed/<name>/ (train.jsonl + val.jsonl)
  - sem `max_samples` arbitrário — usa tudo
  - max_length configurável (default 512)
  - LoRA padrão; QLoRA via flag opcional (requer bitsandbytes)

God: Atena (estratégia) + Hefesto (forja do adapter).
OSL-4:  funções ≤60 linhas.
OSL-15: erro de treino vira TrainResult(success=False), nunca propaga.
OSL-17: só treina; validação/eval ficam em módulo separado (T5).
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_PROCESSED_DIR = Path("data") / "processed"
_TRAINING_DIR  = Path("data") / "training"


@dataclass
class TrainConfig:
    name:          str
    data_dir:      Path
    base_model:    str = "HuggingFaceTB/SmolLM2-135M-Instruct"
    out_dir:       Path | None = None
    # LoRA
    rank:          int = 8
    alpha:         int = 16
    dropout:       float = 0.05
    target_modules: list[str] = field(default_factory=lambda: [
        "q_proj", "o_proj", "v_proj", "k_proj",
    ])
    # Treino
    epochs:        int = 3
    batch_size:    int = 4
    grad_accum:    int = 2
    lr:            float = 5e-5
    max_length:    int = 384 # 512
    warmup_ratio:  float = 0.03
    logging_steps: int = 5
    save_strategy: str = "epoch"
    eval_strategy: str = "epoch"
    patience:      int = 1
    # Hardware
    device:        str = "cpu"
    dtype:         str = "fp32"   # fp32 | fp16 | bf16
    # QLoRA (opcional)
    qlora:         bool = False
    seed:          int = 42


@dataclass
class TrainResult:
    success:       bool
    adapter_dir:   Path | None = None
    trainer_state: dict | None = None
    final_loss:    float | None = None
    val_loss:      float | None = None
    epochs_run:    int = 0
    elapsed_s:     float = 0.0
    errors:        list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Carregamento
# ---------------------------------------------------------------------------

def _load_datasets(data_dir: Path) -> tuple[Any, Any]:
    """Carrega train.jsonl e val.jsonl como datasets HuggingFace."""
    from datasets import load_dataset
    train_path = data_dir / "train.jsonl"
    val_path   = data_dir / "val.jsonl"
    if not train_path.exists():
        raise FileNotFoundError(f"train.jsonl ausente: {train_path}")
    train = load_dataset("json", data_files=str(train_path), split="train")
    if val_path.exists():
        val = load_dataset("json", data_files=str(val_path), split="train")
    else:
        val = None
    return train, val


def _get_dtype(cfg: TrainConfig):
    import torch
    if cfg.dtype == "fp16":
        return torch.float16
    if cfg.dtype == "bf16":
        return torch.bfloat16
    return torch.float32


def _load_model(cfg: TrainConfig):
    """Carrega modelo base + tokenizer. Aplica QLoRA se pedido."""
    try:
        import torch
        import os
        torch.set_num_threads(min(8, os.cpu_count() or 4))
        torch.set_num_interop_threads(1)   # single-threaded interop, evita contention
    except Exception as e:
        from engine.tools.error_info import formated_traceback
        formated_traceback(e, "Encoding Reconfiguration")

    from transformers import AutoModelForCausalLM, AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(cfg.base_model)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    load_kwargs: dict[str, Any] = {
        "dtype":      _get_dtype(cfg),
        "device_map": None,
    }

    if cfg.qlora:
        try:
            from transformers import BitsAndBytesConfig
        except ImportError as exc:
            raise ImportError(
                "QLoRA requer bitsandbytes. Rode "
                "`pip install bitsandbytes` ou use --no-qlora."
            ) from exc
        load_kwargs["quantization_config"] = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_compute_dtype=torch.float32,
            bnb_4bit_use_double_quant=True,
            bnb_4bit_quant_type="nf4",
        )

    try:
        model = AutoModelForCausalLM.from_pretrained(cfg.base_model, **load_kwargs)
    except TypeError:
        load_kwargs.pop("dtype", None)
        load_kwargs["torch_dtype"] = _get_dtype(cfg)
        model = AutoModelForCausalLM.from_pretrained(cfg.base_model, **load_kwargs)
    return model, tokenizer


# ---------------------------------------------------------------------------
# Preparação do dataset
# ---------------------------------------------------------------------------

def _prepare_dataset(train, val, tokenizer, cfg: TrainConfig):
    """Tokeniza manualmente (sem datasets.map) — evita bug de nested labels no v5.x."""
    from datasets import Dataset

    pad_id = tokenizer.pad_token_id or 0
    eos_id = tokenizer.eos_token_id or 0

    def _process_one(sample: dict) -> dict:
        messages = list(sample.get("messages", []))
        if not any(m.get("role") == "system" for m in messages):
            messages = [{"role": "system", "content": "Responda em português de forma clara e direta."}] + messages
        parts = [f"<|im_start|>{m['role']}\n{m['content']}<|im_end|>\n" for m in messages]
        parts.append("<|im_start|>assistant\n")
        text = "".join(parts)

        enc = tokenizer(text, truncation=True, max_length=cfg.max_length, padding=False)
        ids = enc["input_ids"]

        # Unwrap recursivo até ficar plano
        depth = 0
        while isinstance(ids, list) and len(ids) >= 1 and isinstance(ids[0], list):
            ids = ids[0]
            depth += 1
            if depth > 5:
                break

        # Forçar list[int] limpo
        try:
            ids = [int(t) for t in ids]
        except (TypeError, ValueError):
            ids = [eos_id]

        if not ids:
            ids = [eos_id]

        labels = [tok if tok != pad_id else -100 for tok in ids]

        return {
            "input_ids": list(ids),
            "attention_mask": [1] * len(ids),
            "labels": list(labels),
        }

    train_rows = [_process_one(s) for s in train]

    # DIAG: tamanhos dos samples (detecta truncation)
    import sys as _diag_sys
    lens = [len(r["input_ids"]) for r in train_rows]
    if lens:
        truncated = sum(1 for l in lens if l >= cfg.max_length)
        print(
            f"[DIAG] lens: min={min(lens)} max={max(lens)} "
            f"avg={sum(lens)//len(lens)} max_cfg={cfg.max_length} "
            f"truncated={truncated}/{len(lens)}",
            file=_diag_sys.stderr,
        )
        if truncated > 0:
            print(
                f"[WARN-TRUNC] {truncated} samples batendo max_length — @N pode ser cortado",
                file=_diag_sys.stderr,
            )

    # Diagnóstico: garantir que ninguém ficou nested
    for i, row in enumerate(train_rows):
        if row["labels"] and isinstance(row["labels"][0], list):
            raise RuntimeError(f"[DIAG] sample {i} nested labels: {row['labels'][:3]}")
        if any(not isinstance(t, int) for t in row["labels"]):
            raise RuntimeError(f"[DIAG] sample {i} non-int labels: {row['labels'][:3]}")

    tokenized_train = Dataset.from_list(train_rows)

    tokenized_val = None
    if val is not None and len(val) > 0:
        val_rows = [_process_one(s) for s in val]
        tokenized_val = Dataset.from_list(val_rows)

    return tokenized_train, tokenized_val


# ---------------------------------------------------------------------------
# Train
# ---------------------------------------------------------------------------

def train_lora(cfg: TrainConfig) -> TrainResult:
    t0 = time.monotonic()

    # validações
    data_dir = Path(cfg.data_dir)
    if not data_dir.exists():
        return TrainResult(
            success=False,
            errors=[f"data_dir não existe: {data_dir}"],
            elapsed_s=round(time.monotonic() - t0, 2),
        )

    out_dir = Path(cfg.out_dir) if cfg.out_dir else (_TRAINING_DIR / cfg.name)
    if out_dir.exists() and (out_dir / "adapter_model.safetensors").exists():
        return TrainResult(
            success=False,
            errors=[f"adapter já existe em {out_dir} (delete ou use outro --out)"],
            elapsed_s=round(time.monotonic() - t0, 2),
        )

    # imports pesados (depois das validações)
    try:
        import torch
        from transformers import (
            Trainer, TrainingArguments, DataCollatorForLanguageModeling,
            EarlyStoppingCallback,
        )
        from peft import LoraConfig, get_peft_model, TaskType
    except ImportError as exc:
        return TrainResult(
            success=False,
            errors=[f"import falhou: {exc}"],
            elapsed_s=round(time.monotonic() - t0, 2),
        )

    # carrega
    try:
        model, tokenizer = _load_model(cfg)
    except Exception as exc:
        return TrainResult(
            success=False,
            errors=[f"carregar modelo: {exc}"],
            elapsed_s=round(time.monotonic() - t0, 2),
        )

    # LoRA config
    try:
        lora_cfg = LoraConfig(
            task_type=TaskType.CAUSAL_LM,
            r=cfg.rank,
            lora_alpha=cfg.alpha,
            lora_dropout=cfg.dropout,
            target_modules=cfg.target_modules,
            bias="none",
        )
        model = get_peft_model(model, lora_cfg)
    except Exception as exc:
        return TrainResult(
            success=False,
            errors=[f"LoraConfig: {exc}"],
            elapsed_s=round(time.monotonic() - t0, 2),
        )

    # datasets
    try:
        train_ds, val_ds = _load_datasets(data_dir)
        train_tok, val_tok = _prepare_dataset(train_ds, val_ds, tokenizer, cfg)
    except Exception as exc:
        return TrainResult(
            success=False,
            errors=[f"preparar dataset: {exc}"],
            elapsed_s=round(time.monotonic() - t0, 2),
        )

    if len(train_tok) < 2:
        return TrainResult(
            success=False,
            errors=[f"train vazio ({len(train_tok)} amostras)"],
            elapsed_s=round(time.monotonic() - t0, 2),
        )

    # Watchdog: aborta se treino exceder 30min (mitigação de thermal throttle)
    import threading
    _abort = threading.Event()
    def _watchdog():
        if not _abort.wait(timeout=1800):
            print("[WATCHDOG] Treino excedeu 30min — abortando", flush=True)
            import os, signal
            os.kill(os.getpid(), signal.SIGINT)  # força parada do Trainer

    watchdog_thread = threading.Thread(target=_watchdog, daemon=True)
    watchdog_thread.start()

    # TrainingArguments
    has_val = val_tok is not None and len(val_tok) > 0
    args_kwargs: dict[str, Any] = {
        "output_dir":                    str(out_dir),
        "num_train_epochs":              cfg.epochs,
        "per_device_train_batch_size":   cfg.batch_size,
        "gradient_accumulation_steps":   cfg.grad_accum,
        "learning_rate":                 cfg.lr,
        "warmup_ratio":                  cfg.warmup_ratio,
        "logging_steps":                 10, #cfg.logging_steps,
#        "save_strategy":                 "no", #cfg.save_strategy,
        "save_total_limit":              None, #2,
        "report_to":                     "none",
        "use_cpu":                       cfg.device == "cpu",
        "seed":                          cfg.seed,
#        "eval_strategy":                 "no",
        "dataloader_num_workers":        0,
#        "load_best_model_at_end":        False,
        "remove_unused_columns":         False,
        "dataloader_pin_memory":         False,
        "gradient_checkpointing":        False,
        "logging_first_step":            False,
#        "group_by_length":               True,
        "logging_strategy":              "steps",
        "fp16":                          cfg.dtype == "fp16",
        "bf16":                          cfg.dtype == "bf16",
    }
    if has_val:
        args_kwargs["eval_strategy"]              = cfg.eval_strategy   # "epoch"
        args_kwargs["save_strategy"]              = cfg.save_strategy   # "epoch"
        args_kwargs["save_total_limit"]           = 1                  # só o último
        args_kwargs["load_best_model_at_end"]     = True
        args_kwargs["metric_for_best_model"]      = "eval_loss"
        args_kwargs["greater_is_better"]          = False
    else:
        args_kwargs["eval_strategy"]              = "no"
        args_kwargs["save_strategy"]              = "no"
    try:
        training_args = TrainingArguments(**args_kwargs)
    except TypeError as exc:
        # transformers 5.x pode ter renomeado algum arg
        removed = str(exc)
        for key in list(args_kwargs):
            if key in removed:
                args_kwargs.pop(key, None)
        try:
            training_args = TrainingArguments(**args_kwargs)
        except Exception as exc2:
            return TrainResult(
                success=False,
                errors=[f"TrainingArguments: {exc2}"],
                elapsed_s=round(time.monotonic() - t0, 2),
            )

    # Trainer
    callbacks = []
    if has_val and cfg.patience > 0:
        callbacks.append(EarlyStoppingCallback(early_stopping_patience=cfg.patience))

    def _manual_collator(features):
        """Collator manual — força tensores flat, imune a bugs do datasets/transformers v5."""
        import torch
        max_len = max(len(f["input_ids"]) for f in features)
        max_len = ((max_len + 7) // 8) * 8  # pad to multiple of 8

        pad_id = tokenizer.pad_token_id or 0
        input_ids_batch = []
        attention_mask_batch = []
        labels_batch = []

        for f in features:
            ids = list(f["input_ids"])
            mask = list(f["attention_mask"])
            lbl = list(f["labels"])
            pad_len = max_len - len(ids)
            input_ids_batch.append(ids + [pad_id] * pad_len)
            attention_mask_batch.append(mask + [0] * pad_len)
            labels_batch.append(lbl + [-100] * pad_len)

        return {
            "input_ids":      torch.tensor(input_ids_batch,      dtype=torch.long),
            "attention_mask": torch.tensor(attention_mask_batch, dtype=torch.long),
            "labels":         torch.tensor(labels_batch,         dtype=torch.long),
        }

    collator = _manual_collator

    try:
        trainer = Trainer(
            model=model,
            args=training_args,
            train_dataset=train_tok,
            eval_dataset=val_tok if has_val else None,
            data_collator=collator,
            callbacks=callbacks,
        )
        train_output = trainer.train()
    except Exception as exc:
        return TrainResult(
            success=False,
            errors=[f"Trainer.train: {exc}"],
            elapsed_s=round(time.monotonic() - t0, 2),
        )
    finally:
        _abort.set()

    # salva
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
        model.save_pretrained(str(out_dir))
        tokenizer.save_pretrained(str(out_dir))
    except Exception as exc:
        return TrainResult(
            success=False,
            adapter_dir=out_dir,
            errors=[f"salvar adapter: {exc}"],
            elapsed_s=round(time.monotonic() - t0, 2),
        )

    # trainer_state
    trainer_state = None
    state_path = out_dir / "trainer_state.json"
    if state_path.exists():
        try:
            trainer_state = json.loads(state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            trainer_state = None

    final_loss = getattr(train_output, "training_loss", None) if train_output else None
    if final_loss is None:
        try:
            final_loss = float(train_output.metrics.get("train_loss"))
        except Exception:
            final_loss = None

    val_loss = None
    if trainer_state and isinstance(trainer_state.get("log_history"), list):
        for entry in reversed(trainer_state["log_history"]):
            if "eval_loss" in entry:
                val_loss = float(entry["eval_loss"])
                break

    return TrainResult(
        success=True,
        adapter_dir=out_dir,
        trainer_state=trainer_state,
        final_loss=round(float(final_loss), 4) if final_loss is not None else None,
        val_loss=round(val_loss, 4) if val_loss is not None else None,
        epochs_run=cfg.epochs,
        elapsed_s=round(time.monotonic() - t0, 2),
    )
