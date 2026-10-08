# profile_train.py
import time, gc, torch, json
from pathlib import Path
from transformers import AutoTokenizer, AutoModelForCausalLM, DataCollatorForSeq2Seq
from peft import LoraConfig, get_peft_model, TaskType

MODEL_ID = "HuggingFaceTB/SmolLM2-135M-Instruct"
DATASET_PATH = Path("data/training/brunnr_full.jsonl")
MAX_SAMPLES = 64      # Amostra pequena para o profiling ser rápido
STEPS = 15            # Número de iterações de medição
BATCH_SIZE = 4
GRAD_ACC = 2

print("=" * 70)
print("🔬 ORN PROFILER: Análise de Gargalos no Treino LoRA (CPU)")
print("=" * 70)

# 1. Carregamento
t0 = time.perf_counter()
tokenizer = AutoTokenizer.from_pretrained(MODEL_ID)
if tokenizer.pad_token is None: tokenizer.pad_token = tokenizer.eos_token
model = AutoModelForCausalLM.from_pretrained(MODEL_ID, dtype=torch.float32, device_map="cpu")
print(f"[OK] Modelo carregado em {time.perf_counter() - t0:.2f}s")

# 2. Configuração Upper-6 LoRA (Otimizado)
lora_config = LoraConfig(
    task_type=TaskType.CAUSAL_LM, r=8, lora_alpha=16, lora_dropout=0.05,
    target_modules=["q_proj", "v_proj"],
    layers_to_transform=list(range(6, 12)), # Apenas camadas 6 a 11
    layers_pattern="layers",
)
model = get_peft_model(model, lora_config)
model.train()

# 3. Dados (Pré-tokenizados para isolar o gargalo do loop)
print("[INFO] Carregando e tokenizando dados...")
t_data = time.perf_counter()
texts = []
with open(DATASET_PATH, "r", encoding="utf-8") as f:
    for i, line in enumerate(f):
        if i >= MAX_SAMPLES: break
        try: texts.append(json.loads(line).get("text", ""))
        except: pass

tokenized_samples = []
for text in texts:
    enc = tokenizer(text, truncation=True, max_length=256)
    tokenized_samples.append({"input_ids": enc["input_ids"], "labels": list(enc["input_ids"])})
print(f"[OK] Dados preparados em {time.perf_counter() - t_data:.2f}s ({len(tokenized_samples)} amostras)")

collator = DataCollatorForSeq2Seq(tokenizer=tokenizer, padding=True)
optimizer = torch.optim.AdamW(model.parameters(), lr=5e-5)

# 4. Loop de Profiling
print(f"\n[INFO] Executando {STEPS} passos de medição...")
timings = {"fwd": [], "bwd": [], "opt": [], "data": [], "gc": []}

optimizer.zero_grad()
for step in range(1, STEPS + 1):
    # Data Collate
    t_step = time.perf_counter()
    start_i = ((step - 1) * BATCH_SIZE) % len(tokenized_samples)
    batch_slice = tokenized_samples[start_i : start_i + BATCH_SIZE]
    batch = collator(batch_slice)
    timings["data"].append(time.perf_counter() - t_step)
    
    # Forward Pass
    t_fwd = time.perf_counter()
    outputs = model(**batch)
    loss = outputs.loss / GRAD_ACC
    timings["fwd"].append(time.perf_counter() - t_fwd)
    
    # Backward Pass
    t_bwd = time.perf_counter()
    loss.backward()
    timings["bwd"].append(time.perf_counter() - t_bwd)
    
    # Optimizer Step & GC
    if step % GRAD_ACC == 0:
        t_opt = time.perf_counter()
        optimizer.step()
        optimizer.zero_grad()
        timings["opt"].append(time.perf_counter() - t_opt)
        
        t_gc = time.perf_counter()
        gc.collect()
        timings["gc"].append(time.perf_counter() - t_gc)
        
    if step % 5 == 0:
        print(f"  Step {step:02d}/{STEPS} | Loss: {loss.item() * GRAD_ACC:.4f}")

# 5. Relatório Consolidado
print("\n" + "=" * 70)
print("📊 RELATÓRIO DE PROFILING (Médias por Passo)")
print("=" * 70)

def fmt(name, times):
    if not times: return 0.0
    avg = sum(times) / len(times)
    total = sum(times)
    total_all = sum(sum(v) for v in timings.values())
    pct = (total / total_all) * 100 if total_all > 0 else 0
    print(f"  {name:<18} {avg*1000:>7.1f} ms  ({pct:>5.1f}%)  [Total: {total:.2f}s]")
    return total

total_time = 0.0
total_time += fmt("Forward Pass", timings["fwd"])
total_time += fmt("Backward Pass", timings["bwd"])
total_time += fmt("Optimizer Step", timings["opt"])
total_time += fmt("Data Collate", timings["data"])
total_time += fmt("Garbage Coll.", timings["gc"])

print("-" * 70)
print(f"  {'TOTAL':<18} {total_time:>7.1f} ms  (100.0%)  [Total: {total_time:.2f}s]")
print("=" * 70)

print("\n💡 ANÁLISE AUTOMÁTICA DE GARGALOS:")
fwd_pct = (sum(timings["fwd"]) / total_time) * 100
bwd_pct = (sum(timings["bwd"]) / total_time) * 100
data_pct = (sum(timings["data"]) / total_time) * 100

if data_pct > 15:
    print("  ⚠️  Gargalo de Dados (>15%): O collate está lento. Solução: Salvar o dataset já tokenizado em disco (.pt) e usar DataLoader com num_workers>0.")
if bwd_pct > 60:
    print("  ⚠️  Gargalo de Backward (>60%): O cálculo de gradientes domina. Solução: Reduzir `layers_to_transform` (ex: apenas camadas 10-11) ou ativar `gradient_checkpointing=True`.")
if fwd_pct > 30:
    print("  ⚠️  Gargalo de Forward (>30%): A inferência está lenta. Solução: Verificar se o MKL/OneDNN está ativo no PyTorch ou testar `torch.compile`.")

print("\n[OK] Profiling concluído.")
