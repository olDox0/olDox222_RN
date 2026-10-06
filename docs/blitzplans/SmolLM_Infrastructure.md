# docs/blitzplans/SmolLM_Infrastructure.md

# 🧠 Planejamento ORN: Infraestrutura SmolLM 135M (PC-B Bluebaby)

**Protocolo**: ProDeNov v1.0  
**Data**: 2026-10-02  
**Hardware Alvo**: PC-B "Bluebaby" (Dell Inspiron 15 3520)

---

## 📋 1. Contexto e Brainstorming

### Hardware Detectado (systeminfo)
| Componente | Especificação | Implicação |
|---|---|---|
| **CPU** | Intel Family 6 Model 154 (Alder Lake 12th gen) ~1300MHz | ✅ AVX2, AVX, SSE4.2 (diferente do N2808!) |
| **RAM** | 16GB total, ~3.7GB disponível | ✅ Margem confortável para treino |
| **OS** | Windows 11 Pro 26200 | ✅ Toolchain moderna |
| **Storage** | SSD NVMe (Inspiron 3520) | ✅ I/O rápido para datasets |

### Objetivos Declarados
1. **Engenharia Reversa** do SmolLM 135M (dissecar pesos, camadas, tensores)
2. **Orquestração de Treinamento** (LoRA/QLoRA em CPU)
3. **Sistemas Embarcados** (estudar footprint mínimo)
4. **Benchmark Comparativo** vs Qwen 0.5B no N2808

---

## 🔍 2. Análise de Viabilidade

### ✅ Viável (Alta Confiança)
- **SmolLM 135M em GGUF Q4_K_M** → ~85MB RAM (cabe folgado nos 16GB)
- **Inferência CPU** → 10-20 tok/s esperado (vs 1.2 tok/s no N2808)
- **Engenharia Reversa** → 12 camadas, 9 heads de atenção (dissecável)
- **LoRA rank=4/8** → Adapter de ~2-5MB, treinável em CPU

### ⚠️ Riscos (Plano B necessário)
- **Treino full** → Inviável em CPU (dias/semanas) → usar LoRA
- **Dataset grande** → Limitar a 10-50MB para estudo
- **AVX2 não otimizado** → Fallback para SSE4.2 se necessário

### ❌ Fora de Escopo
- Fine-tuning full do modelo base
- Treinamento distribuído
- Modelos >1B parâmetros

---

## 📝 3. Tasklist com Planos A/B/C

### **Fase 1: Aquisição e Validação** (Prioridade: Alta | Prazo: 1 sessão)

| # | Tarefa | Plano A | Plano B | Plano C |
|---|---|---|---|---|
| 1.1 | Download SmolLM-135M-Instruct GGUF | HuggingFace (Q4_K_M) | Q2_K se Q4 falhar | Converter de safetensors |
| 1.2 | Validação de integridade | SHA256 + teste de carga | Teste de inferência básica | Skip se hash OK |
| 1.3 | Perfil de memória base | Medir RAM/CPU em idle | Comparar com Qwen 0.5B | Documentar baseline |

### **Fase 2: Engenharia Reversa** (Prioridade: Alta | Prazo: 2 sessões)

| # | Tarefa | Plano A | Plano B | Plano C |
|---|---|---|---|---|
| 2.1 | Parser de cabeçalho GGUF | Script Python (gguf library) | Leitura binária direta (C) | Usar `gguf-py` oficial |
| 2.2 | Mapeamento de tensores | Extrair Wq, Wk, Wv, Wo, FFN | Visualizar em heatmap | Exportar para JSON |
| 2.3 | Correlação código↔pesos | Mapear `orn_llama_wrapper.c` | Documentar fluxo de dados | Criar diagrama arquitetural |

### **Fase 3: Pipeline de Treinamento** (Prioridade: Média | Prazo: 3 sessões)

| # | Tarefa | Plano A | Plano B | Plano C |
|---|---|---|---|---|
| 3.1 | Dataset mínimo (JSONL) | 10MB de código Python | 5MB de texto técnico | Gerar sinteticamente |
| 3.2 | Tokenização compatível | Usar tokenizer do SmolLM | Fallback para Qwen tokenizer | Custom vocab |
| 3.3 | LoRA adapter (rank=4) | `llama.cpp` CLI | `peft` + `transformers` | Implementar do zero (C) |
| 3.4 | Loop de treino (1 epoch) | 100 steps, lr=1e-4 | 50 steps, lr=5e-5 | Skip se crashar |

### **Fase 4: Orquestração e Telemetria** (Prioridade: Baixa | Prazo: 2 sessões)

| # | Tarefa | Plano A | Plano B | Plano C |
|---|---|---|---|---|
| 4.1 | BridgeConfig dedicado | `memory_profile="smol"` | Ajustar `n_ctx`, `n_batch` | Hardcoded no código |
| 4.2 | Telemetria de treino | JSONL com loss, lr, step | CSV simples | Print no stdout |
| 4.3 | Comparativo de performance | SmolLM vs Qwen 0.5B | Benchmark de tok/s | Documentar diferenças |

---

## 📂 4. Placeholders (Estrutura de Arquivos)

```
ORN_proj/
├── models/
│   └── smol/
│       └── SmolLM2-135M-Instruct-Q4_K_M.gguf  # Fase 1
│
├── engine/
│   ├── tools/
│   │   ├── gguf_inspector.py  # Fase 2: parser de GGUF
│   │   └── tensor_mapper.py   # Fase 2: visualização de pesos
│   │
│   └── training/
│       ├── __init__.py
│       ├── dataset_loader.py  # Fase 3: carrega JSONL
│       ├── lora_trainer.py    # Fase 3: LoRA em CPU
│       └── telemetry.py       # Fase 4: log de treino
│
├── data/
│   └── training/
│       ├── python_code.jsonl  # Fase 3: dataset mínimo
│       └── lora_adapter.bin   # Fase 3: pesos treinados
│
└── docs/
    └── SmolLM_Infrastructure.md  # Documentação técnica
```

---

## 🔧 5. Questões Técnicas

### 5.1 Toolchain
- **Compilador**: winlibs (GCC 16.2) já instalado → usar `-march=alderlake -O3`
- **Python**: 3.12.4 (compatível com `llama-cpp-python`)
- **Dependências**: `gguf`, `safetensors`, `peft` (opcional)

### 5.2 Otimizações CPU
```bash
# Flags para Alder Lake (AVX2, FMA)
CMAKE_ARGS="-DGGML_AVX2=ON -DGGML_FMA=ON -DGGML_OPENMP=ON"
CMAKE_C_FLAGS="-march=alderlake -O3 -fopenmp"
```

### 5.3 Diagnóstico (ProDeNov 3.1.4)
- **Onde?**: `engine/training/lora_trainer.py`
- **O que?**: Perda de memória durante treino
- **Quando?**: Após 50 steps
- **Por que?**: KV-cache não liberado
- **Solução**: Chamar `gc.collect()` + `torch.cuda.empty_cache()` (se GPU)

---

## 🎯 6. Roteiro de Implementação (RIT/Ritual)

### **Sessão 1: Fundação** (Hoje)
1. ✅ Download SmolLM 135M GGUF
2. ✅ Validação de integridade
3. ✅ Perfil de memória base
4. ✅ Criar `BridgeConfig` dedicado

### **Sessão 2: Engenharia Reversa**
1. ✅ Parser de GGUF (`gguf_inspector.py`)
2. ✅ Mapeamento de tensores
3. ✅ Documentação arquitetural

### **Sessão 3: Treinamento**
1. ✅ Preparar dataset mínimo
2. ✅ Implementar LoRA trainer
3. ✅ Teste de 1 epoch (100 steps)

### **Sessão 4: Orquestração**
1. ✅ Telemetria de treino
2. ✅ Benchmark comparativo
3. ✅ Documentação final

---

# ⚡ BLITZPLAN: Infraestrutura SmolLM 135M (PC-B Bluebaby)
**Protocolo**: ProDeNov v1.0 | **Data**: 2026-10-02  
**Hardware Alvo**: Dell Inspiron 15 3520 (i5-1235U, 16GB RAM, AVX2)  
**Status**: 🟡 Planejamento Concluído | 🟢 Pronto para Fase 1  

---

## 1. Brainstorming & Análise de Viabilidade
- **Objetivo**: Habilitar inferência e estudo de orquestração de treinamento (LoRA) do SmolLM2-135M no ORN.
- **Viabilidade**: **Alta**. O modelo Q4_K_M tem ~85MB. Cabe folgado na RAM, permitindo estudo de LoRA (rank 4/8) sem esgotar a memória do PC-B.
- **Manutenção**: Baixa. Utiliza a stack `llama.cpp` já estabilizada no projeto.
- **Escalabilidade**: O footprint minúsculo permite portabilidade futura para sistemas embarcados (RISC, 32-bit) sem refatoração massiva.
- **Risco Principal**: Vazamento de memória durante loops de treino em Python. Mitigado pelo módulo de telemetria e `gc.collect()`.

---

## 2. Tasklist & Checklist (Planos A, B, C)

### Fase 1: Aquisição e Configuração (Prioridade: Alta | Prazo: 1 sessão)
- [ ] **1.1 Download do Modelo**
  - *Plano A*: Baixar `SmolLM2-135M-Instruct-Q4_K_M.gguf` via HuggingFace (recomendado).
  - *Plano B*: Usar versão `Q2_K` (~50MB) se a Q4 apresentar lentidão inesperada.
  - *Plano C*: Converter de `safetensors` localmente via `llama.cpp` (fallback).
- [ ] **1.2 Configuração do Bridge**
  - *Plano A*: Criar perfil `memory_profile="smol"` no `BridgeConfig` (n_ctx=1024, n_threads=4).
  - *Plano B*: Hardcode dos parâmetros no `llm_bridge.py` se o perfil falhar.

### Fase 2: Pipeline de Dados (Prioridade: Alta | Prazo: 1 sessão)
- [ ] **2.1 Criação do Dataset**
  - *Plano A*: Montar `data/training/python_code.jsonl` com 10MB de snippets Python limpos.
  - *Plano B*: Gerar dataset sintético mínimo (500 linhas) para teste de fluxo.
  - *Plano C*: Usar subset de 1% de um dataset público (ex: TheStack).
- [ ] **2.2 Implementação do Loader**
  - *Plano A*: `dataset_loader.py` lendo JSONL e tokenizando via `TokenizerBridge`.
  - *Plano B*: Leitura direta de texto plano com chunking fixo.

### Fase 3: Orquestração de Treinamento LoRA (Prioridade: Média | Prazo: 2 sessões)
- [ ] **3.1 Script de Treino**
  - *Plano A*: Orquestrar CLI do `llama.cpp` (`llama-quantize` / `llama-finetune`) via `subprocess` em `lora_trainer.py`.
  - *Plano B*: Usar bindings Python do `llama-cpp-python` se a CLI falhar.
  - *Plano C*: Implementar loop de treino customizado em C (adiado, alta complexidade).
- [ ] **3.2 Telemetria**
  - *Plano A*: `telemetry.py` registrando `step`, `loss`, `lr` e `tempo` em JSONL.
  - *Plano B*: Print direto no stdout com redirecionamento para arquivo.

### Fase 4: Integração e Revisão de Regressão (Prioridade: Alta | Prazo: 1 sessão)
- [ ] **4.1 Teste de Inferência com Adapter**
  - *Plano A*: Carregar `lora_adapter.bin` junto ao modelo base e testar geração.
  - *Plano B*: Validar apenas o carregamento sem geração (sanity check).
- [ ] **4.2 Revisão de Regressão**
  - *Check*: Garantir que o `Qwen2.5-Coder-0.5B` continua funcionando normalmente com as novas configurações.

---

## 3. Placeholders (Esboço dos Arquivos)

### `engine/training/dataset_loader.py`
```python
# RAIZ/engine/training/dataset_loader.py
"""
Carregamento e preparação de datasets JSONL para treinamento LoRA.
Objetivo: Ler dados, validar schema e tokenizar usando o vocabulário do modelo.
"""
import json
from pathlib import Path
from typing import Iterator, List

# TODO: Integrar com TokenizerBridge do ORN para tokenização real
def load_jsonl(path: str | Path) -> Iterator[dict]:
    """Yield dicionários de um arquivo JSONL linha por linha."""
    with open(path, 'r', encoding='utf-8') as f:
        for line in f:
            yield json.loads(line)

def prepare_dataset(dataset_path: str | Path, max_samples: int = 1000) -> List[str]:
    """Extrai e prepara textos do dataset para o loop de treino."""
    texts = []
    for i, item in enumerate(load_jsonl(dataset_path)):
        if i >= max_samples:
            break
        # Assume schema: {"text": "..."} ou {"prompt": "...", "completion": "..."}
        text = item.get("text") or f"{item.get('prompt', '')}\n{item.get('completion', '')}"
        if text:
            texts.append(text.strip())
    return texts
```

### `engine/training/lora_trainer.py`
```python
# RAIZ/engine/training/lora_trainer.py
"""
Orquestrador de treinamento LoRA para SmolLM 135M.
Objetivo: Gerenciar o processo de fine-tuning via CLI do llama.cpp ou bindings.
"""
import subprocess
import sys
from pathlib import Path
from engine.training.telemetry import log_step, save_metrics

def train_lora(
    model_path: str | Path,
    dataset_path: str | Path,
    output_adapter: str | Path,
    epochs: int = 1,
    lr: float = 1e-4,
    rank: int = 4
) -> bool:
    """
    Executa o treinamento LoRA.
    Fluxo: Valida paths -> Configura args -> Executa subprocess -> Log de telemetria.
    """
    log_step("INICIO", f"Treinamento LoRA: rank={rank}, lr={lr}, epochs={epochs}")
    
    # Plano A: Orquestração via CLI do llama.cpp (mais estável em CPU)
    # Nota: Ajustar o caminho do executável conforme a instalação do winlibs
    cmd = [
        sys.executable, "-m", "llama_cpp.server", # Placeholder: substituir por comando real de finetune
        "--model", str(model_path),
        "--lora", str(output_adapter),
        "--lora-train", str(dataset_path),
        "--epochs", str(epochs),
        "--lora-rank", str(rank),
        "--learning-rate", str(lr)
    ]
    
    try:
        # Em produção, usar subprocess.Popen com stream de stdout para telemetria em tempo real
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        log_step("SUCESSO", "Treinamento concluído com sucesso.")
        save_metrics({"status": "success", "output": output_adapter})
        return True
    except subprocess.CalledProcessError as e:
        log_step("ERRO", f"Falha no treinamento: {e.stderr}")
        save_metrics({"status": "error", "details": e.stderr})
        return False
```

### `engine/training/telemetry.py`
```python
# RAIZ/engine/training/telemetry.py
"""
Telemetria leve para loops de treinamento.
Objetivo: Registrar métricas de desempenho e integridade sem sobrecarregar o sistema.
"""
import json
import time
from pathlib import Path

TELEMETRY_FILE = Path("telemetry/training_run.jsonl")

def log_step(phase: str, message: str) -> None:
    """Log formatado no console com timestamp."""
    ts = time.strftime("%H:%M:%S")
    print(f"[{ts}] [{phase.upper()}] {message}")

def save_metrics(metrics: dict) -> None:
    """Anexa métricas ao arquivo de telemetria de forma segura."""
    TELEMETRY_FILE.parent.mkdir(parents=True, exist_ok=True)
    metrics["timestamp"] = time.time()
    with open(TELEMETRY_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(metrics, ensure_ascii=False) + "\n")
```

---

## 4. Questões Técnicas & Sistema de Diagnóstico (Typhon/ProDeNov 3.1.4)

- **Onde?**: `engine/training/lora_trainer.py` (loop de treino).
- **O que?**: Possível vazamento de memória (RAM crescendo progressivamente).
- **Quem?**: Módulo de treino, garbage collector do Python e backend `llama.cpp`.
- **Quando?**: Após 50-100 steps de treinamento.
- **Por que?**: Acúmulo de tensores no gráfico computacional ou cache do KV não liberado entre iterações.
- **Origem**: Comportamento conhecido de bindings Python que não liberam memória C++ imediatamente.
- **Consequência**: O sistema operacional começa a usar swap, travando a máquina (Space Plague / OOM).
- **Solução (Plano B)**: Inserir `import gc; gc.collect()` a cada N steps. Limitar `max_samples` no dataset para testes iniciais. Usar `--dry-run` no comando de treino para validar o fluxo sem executar o loop pesado.

---

## 5. Revisão de Regressão (Checklist Final)
- [ ] O comando `orn think` com o modelo Qwen 0.5B ainda responde corretamente?
- [ ] O perfil de memória `low` ou `smol` não quebrou a inicialização do `SiCDoxBridge`?
- [ ] Os arquivos gerados em `data/training/` estão dentro do limite de 50KB (para o dataset de teste)?

---

## 📋 Roteiro de Implementação e Testagem (RIT)

### 🎬 ATO 1 — Download do Modelo GGUF

**Objetivo**: Obter `SmolLM2-135M-Instruct-Q4_K_M.gguf` (~85MB) em `models/smol_sys/`

#### Plano A (Recomendado): Download via `curl`
```cmd
cd C:\Users\Victor Alexandre\Documents\ORN_proj
mkdir models\smol_sys 2>nul
curl -L -o models\smol_sys\SmolLM2-135M-Instruct-Q4_K_M.gguf ^
  "https://huggingface.co/HuggingFaceTB/SmolLM2-135M-Instruct-GGUF/resolve/main/smollm2-135m-instruct-q4_k_m.gguf"
```

#### Plano B (Fallback): Download via Python
```cmd
python -c "import urllib.request; urllib.request.urlretrieve('https://huggingface.co/HuggingFaceTB/SmolLM2-135M-Instruct-GGUF/resolve/main/smollm2-135m-instruct-q4_k_m.gguf', 'models/smol_sys/SmolLM2-135M-Instruct-Q4_K_M.gguf'); print('OK')"
```

#### Plano C (Fallback): Versão Q2_K (~50MB) se Q4 falhar
```cmd
curl -L -o models\smol_sys\SmolLM2-135M-Instruct-Q2_K.gguf ^
  "https://huggingface.co/HuggingFaceTB/SmolLM2-135M-Instruct-GGUF/resolve/main/smollm2-135m-instruct-q2_k.gguf"
```

#### ✅ Critérios de Validação (Typhon)
```cmd
:: Verificar tamanho do arquivo (esperado: ~80-90MB para Q4_K_M)
dir models\smol_sys\*.gguf
:: Esperado: arquivo entre 80.000.000 e 95.000.000 bytes

:: Validar magic number do GGUF (deve começar com "GGUF")
python -c "f=open('models/smol_sys/SmolLM2-135M-Instruct-Q4_K_M.gguf','rb'); print('Magic:', f.read(4)); f.close()"
:: Esperado: Magic: b'GGUF'
```

---

### 🎬 ATO 2 — Criação do Perfil `smol` no BridgeConfig

**Objetivo**: Adicionar perfil de memória dedicado ao SmolLM em `engine/core/llm_bridge.py`

#### Plano A: Modificação via `doxoade moddify`
```cmd
doxoade moddify replace engine\core\llm_bridge.py -l 58-100 ^
  "model_path:    Path = Path(" ^
  "model_path:    Path = Path("
```

**Edição manual recomendada** (mais segura):
Localizar no `engine/core/llm_bridge.py` a classe `BridgeConfig` e adicionar:

```python
# NOVO: Perfil dedicado para SmolLM 135M
@classmethod
def smol_profile(cls) -> "BridgeConfig":
    """Perfil otimizado para SmolLM2-135M no PC-B Bluebaby.
    Modelo pequeno (~85MB Q4_K_M), cabe folgado em 16GB RAM.
    Aproveita AVX2 do i5-1235U (diferente do N2808).
    """
    return cls(
        model_path=Path("models/smol_sys/SmolLM2-135M-Instruct-Q4_K_M.gguf"),
        memory_profile="default",
        n_ctx=2048,              # SmolLM suporta até 8192, mas 2048 é seguro
        active_window=1024,
        n_batch=256,             # Maior que N2808 (tinha 64)
        n_threads=8,             # i5-1235U tem 10 cores (2P+8E)
        n_threads_batch=8,
        n_gpu_layers=0,          # CPU-only
        use_mmap=True,
        use_mlock=False,         # Não precisa travar - modelo pequeno
        no_alloc=True,
        pin_threads=True,
        cont_batching=True,
        ttl_seconds=1800,        # 30min - modelo carrega rápido
        max_tokens=2048,
        temperature=0.5,
        top_p=0.9,
        top_k=40,
        repeat_penalty=1.1,
        min_p=0.05,
        flash_attn=True,         # i5-1235U suporta
        system_prompt="succinct response. portuguese language"
    )
```

#### ✅ Critérios de Validação
```cmd
python -c "from engine.core.llm_bridge import BridgeConfig; cfg=BridgeConfig.smol_profile(); print(f'Modelo: {cfg.model_path}'); print(f'Existe: {cfg.model_path.exists()}'); print(f'n_ctx={cfg.n_ctx}, threads={cfg.n_threads}')"
```
**Esperado**: `Existe: True`, `n_ctx=2048`, `threads=8`

---

### 🎬 ATO 3 — Teste de Inferência Direta

**Objetivo**: Validar que o SmolLM carrega e responde via `llama-cpp-python`

#### Plano A: Script de teste isolado
Criar `tests/test_smol_basic.py`:

```python
# tests/test_smol_basic.py
"""Teste básico de inferência do SmolLM 135M.
Objetivo: validar carregamento + primeira resposta.
Typhon: onde=tests/, oque=inferência, quem=llama-cpp-python
quando=após download, porquê=validar pipeline, origem=modelo GGUF
consequência=se falhar, revisar BridgeConfig.smol_profile()
"""
import time
from pathlib import Path

def test_smol_load():
    """Plano A: Carrega modelo e faz 1 inferência."""
    from llama_cpp import Llama
    from engine.core.llm_bridge import BridgeConfig
    
    cfg = BridgeConfig.smol_profile()
    if not cfg.model_path.exists():
        print(f"[ERRO] Modelo não encontrado: {cfg.model_path}")
        return False
    
    print(f"[INFO] Carregando {cfg.model_path.name}...")
    t0 = time.perf_counter()
    llm = Llama(
        model_path=str(cfg.model_path),
        n_ctx=cfg.n_ctx,
        n_threads=cfg.n_threads,
        n_batch=cfg.n_batch,
        n_gpu_layers=cfg.n_gpu_layers,
        verbose=False,
    )
    load_ms = (time.perf_counter() - t0) * 1000
    print(f"[OK] Modelo carregado em {load_ms:.0f}ms")
    
    print("[INFO] Testando inferência...")
    t0 = time.perf_counter()
    output = llm(
        "<|im_start|>system\nsuccinct response. portuguese language<|im_end|>\n"
        "<|im_start|>user\nOla, conte ate 3.<|im_end|>\n"
        "<|im_start|>assistant\n",
        max_tokens=32,
        temperature=0.5,
        stop=["<|im_end|>"],
    )
    infer_ms = (time.perf_counter() - t0) * 1000
    text = output["choices"][0]["text"].strip()
    tokens = output["usage"]["completion_tokens"]
    tps = tokens / (infer_ms / 1000) if infer_ms > 0 else 0
    
    print(f"[OK] Resposta: {text!r}")
    print(f"[OK] Tempo: {infer_ms:.0f}ms | Tokens: {tokens} | {tps:.2f} tok/s")
    
    llm.close()
    return True

if __name__ == "__main__":
    ok = test_smol_load()
    print(f"\n{'✔ SUCESSO' if ok else '✘ FALHA'}")
```

#### Execução
```cmd
python tests/test_smol_basic.py
```

#### ✅ Critérios de Sucesso (Typhon)
| Métrica | Mínimo Aceitável | Ideal |
|---|---|---|
| Tempo de carga | < 10s | < 3s |
| Tempo de inferência (32 tok) | < 10s | < 3s |
| Tokens/segundo | > 5 tok/s | > 15 tok/s |
| Resposta não-vazia | Sim | Coerente |

#### Plano B (Fallback): Se `llama_cpp` falhar com SmolLM
```cmd
:: Verificar se o modelo é compatível com a versão do llama-cpp
python -c "import llama_cpp; print('Versão:', llama_cpp.__version__)"
:: Se versão < 0.3.5, SmolLM2 pode não ser suportado (arquitetura diferente)
:: Solução: atualizar llama-cpp-python
pip install llama-cpp-python --upgrade --force-reinstall
```

#### Plano C (Fallback): Usar `orn.dll` nativo
Se `llama-cpp-python` falhar, testar via wrapper C nativo:
```cmd
python -c "
from ctypes import cdll, c_char_p, c_int, create_string_buffer
import os
os.add_dll_directory(r'C:\winlibs\mingw64\bin')
lib = cdll.LoadLibrary(r'native/orn.dll')
lib.orn_init.argtypes = [c_char_p, c_int, c_int]
rc = lib.orn_init(b'models/smol_sys/SmolLM2-135M-Instruct-Q4_K_M.gguf', 2048, 8)
print(f'orn_init rc={rc}')
"
```

---

### 🎬 ATO 4 — Comparativo de Performance (Baseline)

**Objetivo**: Estabelecer baseline SmolLM vs Qwen 0.5B para futuras decisões

#### Script de benchmark
Criar `tests/bench_smol_vs_qwen.py`:

```python
# tests/bench_smol_vs_qwen.py
"""Benchmark comparativo SmolLM 135M vs Qwen 0.5B.
Gera baseline para decisões arquiteturais futuras.
"""
import time
from pathlib import Path
from llama_cpp import Llama

PROMPTS = [
    ("curto", "Ola, tudo bem?", 32),
    ("medio", "Explique recursao em 2 linhas.", 64),
    ("codigo", "Faça quicksort em python.", 128),
]

def bench_model(name: str, model_path: Path, n_threads: int):
    print(f"\n{'='*60}")
    print(f"MODELO: {name}")
    print(f"{'='*60}")
    
    llm = Llama(
        model_path=str(model_path),
        n_ctx=2048, n_threads=n_threads,
        n_batch=256, n_gpu_layers=0, verbose=False,
    )
    
    for label, prompt, max_tok in PROMPTS:
        full = (
            "<|im_start|>system\nsuccinct response. portuguese<|im_end|>\n"
            f"<|im_start|>user\n{prompt}<|im_end|>\n"
            "<|im_start|>assistant\n"
        )
        t0 = time.perf_counter()
        out = llm(full, max_tokens=max_tok, temperature=0.5, stop=["<|im_end|>"])
        ms = (time.perf_counter() - t0) * 1000
        tok = out["usage"]["completion_tokens"]
        tps = tok / (ms / 1000) if ms > 0 else 0
        print(f"  [{label:6s}] {ms:7.0f}ms | {tok:3d} tok | {tps:5.2f} tok/s")
    
    llm.close()

if __name__ == "__main__":
    # Qwen 0.5B (atual)
    qwen = Path("models/sicdox/qwen2.5-coder-0.5b-instruct-q2_k.gguf")
    if qwen.exists():
        bench_model("Qwen 0.5B Q2_K (N2808 baseline)", qwen, n_threads=4)
    
    # SmolLM 135M (novo)
    smol = Path("models/smol_sys/SmolLM2-135M-Instruct-Q4_K_M.gguf")
    if smol.exists():
        bench_model("SmolLM 135M Q4_K_M (PC-B)", smol, n_threads=8)
    else:
        print(f"[ERRO] SmolLM não encontrado: {smol}")
```

#### Execução
```cmd
python tests/bench_smol_vs_qwen.py
```

#### ✅ Critérios de Sucesso
- SmolLM deve ser **pelo menos 3x mais rápido** que Qwen 0.5B em tok/s
- SmolLM deve carregar em **menos de 5s** (vs ~80s do Qwen no N2808)
- Respostas devem ser **legíveis** (mesmo que menos precisas)

---

## 🚦 Checklist de Execução (Fase 1)

```markdown
[ ] ATO 1: Download do SmolLM 135M GGUF
    [ ] Arquivo baixado em models/smol_sys/
    [ ] Tamanho entre 80-95MB (Q4_K_M)
    [ ] Magic number "GGUF" validado
    
[ ] ATO 2: Perfil smol_profile() criado
    [ ] Método adicionado em BridgeConfig
    [ ] Import funciona sem erro
    [ ] model_path.exists() == True
    
[ ] ATO 3: Inferência direta validada
    [ ] Modelo carrega em < 10s
    [ ] Primeira resposta gerada
    [ ] Tokens/segundo > 5
    
[ ] ATO 4: Benchmark comparativo
    [ ] SmolLM vs Qwen medido
    [ ] Dados registrados em docs/
    [ ] Decisão documentada: usar SmolLM como padrão?
```

---

## 🔍 Sistema de Diagnóstico (Typhon)

| Pergunta | Resposta Esperada |
|---|---|
| **Onde?** | `models/smol_sys/`, `engine/core/llm_bridge.py`, `tests/` |
| **O que?** | Download + configuração + inferência + benchmark |
| **Quem?** | `BridgeConfig.smol_profile()`, `llama_cpp.Llama` |
| **Quando?** | Agora (Fase 1 do Blitzplan) |
| **Quanto?** | ~85MB RAM, ~30min de desenvolvimento |
| **Por que?** | Estudar orquestração de treino em hardware modesto |
| **Origem?** | Decisão estratégica de adiar engenharia reversa |
| **Consequência?** | Se falhar: Plano B (Q2_K) ou Plano C (orn.dll nativo) |

---


# 🎯 RIT — ATO 1: Preparação do Ambiente "Lite" para LoRA (PC-B Bluebaby)

**Protocolo**: ProDeNov v1.0 | **Hardware**: PC-B Bluebaby (i5-1235U, 16GB RAM, AVX2)  
**Data**: 2026-10-02 | **Status**: 🟢 Pronto para Execução  
**Foco**: Sistema "lite" para portabilidade máxima

---

## 🧠 Brainstorming & Análise de Viabilidade (ProDeNov 1.1)

### Caminhos "Lite" para LoRA

| Caminho | Dependências | Tamanho | Portabilidade | Complexidade | Educacional |
|---|---|---|---|---|---|
| **L1**: `llama.cpp` CLI nativo | Zero (C puro) | ~10MB | ⭐⭐⭐⭐⭐ | 🔴 Alta (compilação) | ⭐⭐⭐⭐⭐ |
| **L2**: `llama-cpp-python` LoRA | `llama-cpp-python` | ~50MB | ⭐⭐⭐⭐ | 🟡 Média | ⭐⭐⭐⭐ |
| **L3**: `peft` + `transformers` CPU | PyTorch CPU + transformers + peft | ~3GB | ⭐⭐⭐ | 🟢 Baixa | ⭐⭐⭐⭐⭐ |

### Recomendação: **Caminho L1 → L2 → L3** (ordem de tentativa)

**Por que L1 é o ideal para "lite + portabilidade":**
1. **Zero dependências Python** além do que já temos (`llama-cpp-python` para inferência)
2. **Binário C puro** (~10MB), portável para qualquer sistema com GCC
3. **Evita o "Space Plague"** e outros incidentes de compilação no Windows
4. **Alinhado com a filosofia ORN**: CPU-first, minimalismo, previsibilidade

**Risco (ProDeNov 0.2):** Compilar `llama.cpp finetune` no Windows pode cair no **Rabbit Hole** do Incidente I-007 (`CreateFile2`). Mitigação: ter o Plano B (L2) e Plano C (L3) prontos.

---

## 📋 Tasklist com Planos A/B/C (ProDeNov 1.2)

### **ATO 1.1: Verificar Suporte Nativo a LoRA no `llama-cpp-python`** (Prioridade: Alta | Prazo: 2min)

| # | Tarefa | Plano A | Plano B | Plano C |
|---|---|---|---|---|
| 1.1.1 | Verificar API do `llama-cpp-python` | `python -c "from llama_cpp import Llama; print(dir(Llama))"` | Documentação oficial | Skip se L1 falhar |
| 1.1.2 | Testar método `train_lora()` ou similar | Se existir, usar diretamente | Fallback para L2 | Fallback para L3 |

**Critério de sucesso**: Identificar se `Llama` tem método de treino LoRA (ex: `train_lora()`, `finetune()`, `lora_train()`).

---

### **ATO 1.2: Preparar Ambiente para `llama.cpp` CLI (Plano L1)** (Prioridade: Alta | Prazo: 10min)

| # | Tarefa | Plano A | Plano B | Plano C |
|---|---|---|---|---|
| 1.2.1 | Verificar se `llama-finetune` já existe | `where llama-finetune` ou `dir native\*.exe` | Compilar do `llama.cpp` source | Skip se L2/L3 |
| 1.2.2 | Se não existir, clonar `llama.cpp` | `git clone https://github.com/ggerganov/llama.cpp` | Download ZIP | Usar wheel pré-compilada |
| 1.2.3 | Compilar com suporte a finetune | `cmake -B build -DLLAMA_BUILD_EXAMPLES=ON` + `cmake --build build --config Release` | Usar `make` se MinGW | Fallback para L2 |

**Critério de sucesso**: Binário `llama-finetune.exe` (ou similar) disponível em `native/` ou `build/bin/Release/`.

---

### **ATO 1.3: Fallback para `peft` CPU-only (Plano L3)** (Prioridade: Média | Prazo: 15min)

| # | Tarefa | Plano A | Plano B | Plano C |
|---|---|---|---|---|
| 1.3.1 | Instalar PyTorch CPU-only | `pip install torch --index-url https://download.pytorch.org/whl/cpu` | Versão estável via PyPI | Pular |
| 1.3.2 | Instalar `transformers` + `peft` | `pip install transformers peft datasets` | Versões pinned | Fallback para `trl` |
| 1.3.3 | Validar imports | `python -c "import torch, transformers, peft"` | Teste isolado | Skip se B.1.1 falhar |

**Critério de sucesso**: `torch`, `transformers`, `peft` importam sem erro.

---

## 🎬 RIT (Roteiro de Implementação e Testagem)

### **PASSO 1: Verificação Rápida do `llama-cpp-python` (ATO 1.1)**

Execute este comando para ver se a API expõe métodos de treino:

```cmd
python -c "from llama_cpp import Llama; methods = [m for m in dir(Llama) if 'train' in m.lower() or 'lora' in m.lower() or 'finetune' in m.lower()]; print('Métodos de treino/LoRA:', methods if methods else 'NENHUM ENCONTRADO')"
```

**Esperado**: Lista de métodos ou "NENHUM ENCONTRADO".

---

### **PASSO 2: Verificar se `llama-finetune` já existe (ATO 1.2.1)**

```cmd
where llama-finetune 2>nul || echo "Não encontrado no PATH"
dir native\*.exe 2>nul || echo "Nenhum .exe em native/"
dir build\bin\Release\*.exe 2>nul || echo "Nenhum .exe em build/bin/Release/"
```

**Esperado**: Se encontrar `llama-finetune.exe` ou similar, pule para o **ATO 2** (orquestração). Se não, continue para o **PASSO 3**.

---

### **PASSO 3: Clonar e Compilar `llama.cpp` (ATO 1.2.2 - 1.2.3)**

> **⚠️ Nota de Pragmatismo (ProDeNov 4.3):** Este passo pode levar 10-30 minutos e pode falhar por causa do Incidente I-007. Se você preferir evitar o rabbit hole, pule direto para o **PASSO 4** (Plano L3 com `peft`).

```cmd
:: 1. Clonar llama.cpp (se ainda não clonado)
if not exist "thirdparty\llama.cpp" (
    mkdir thirdparty 2>nul
    git clone --depth 1 https://github.com/ggerganov/llama.cpp thirdparty\llama.cpp
) else (
    echo "llama.cpp já clonado"
)

:: 2. Configurar CMake com suporte a exemplos (inclui finetune)
cd thirdparty\llama.cpp
cmake -B build -DLLAMA_BUILD_EXAMPLES=ON -DLLAMA_NATIVE=ON -DLLAMA_AVX2=ON

:: 3. Compilar (pode levar 5-15 minutos no i5-1235U)
cmake --build build --config Release --target llama-finetune -j 8

:: 4. Verificar se o binário foi gerado
dir build\bin\Release\llama-finetune.exe
cd ..\..
```

**Critério de sucesso**: `build/bin/Release/llama-finetune.exe` existe.

---

### **PASSO 4: Fallback para `peft` CPU-only (ATO 1.3)**

Se o **PASSO 3** falhar ou você preferir evitar a compilação C++, execute:

```cmd
:: 1. Instalar PyTorch CPU-only (~800MB)
pip install torch --index-url https://download.pytorch.org/whl/cpu

:: 2. Instalar transformers + peft + datasets
pip install transformers peft datasets accelerate

:: 3. Validar imports
python -c "import torch, transformers, peft, datasets; print(f'torch={torch.__version__}'); print(f'transformers={transformers.__version__}'); print(f'peft={peft.__version__}'); print(f'CUDA: {torch.cuda.is_available()}')"
```

**Critério de sucesso**: Todos os imports funcionam, `CUDA=False` (esperado, usamos CPU).

---

# ⚡ BLITZPLAN: Infraestrutura SmolLM 135M (PC-B Bluebaby)
**Protocolo**: ProDeNov v1.0 | **Data**: 2026-10-02  
**Hardware Alvo**: Dell Inspiron 15 3520 (i5-1235U, 16GB RAM, AVX2)  
**Status**: 🟢 Fases 1-4 Concluídas | 🟡 Fase 5 (Treino Real) Pendente

---

## 1. Resultados Reais (Benchmark 2026-10-02)

### Performance SmolLM 135M vs Qwen 0.5B

| Métrica | SmolLM 135M Q4_K_M | Qwen 0.5B Q2_K | Ganho |
|---|---|---|---|
| Tamanho do modelo | 105 MB | ~379 MB | **3.6x menor** |
| Tempo de carga | 192 ms | 910 ms | **4.7x mais rápido** |
| Velocidade (curto) | 74.71 tok/s | 23.61 tok/s | **3.2x** |
| Velocidade (médio) | 109.84 tok/s | 42.41 tok/s | **2.6x** |
| Velocidade (código) | 116.39 tok/s | 45.99 tok/s | **2.5x** |
| RAM estimada | ~150 MB | ~500 MB | **3.3x menor** |

### Qualidade das Respostas (Baseline)
- **SmolLM**: Responde em inglês/português misturado, alucina em instruções complexas
- **Qwen**: Coerente em português, segue system_prompt, melhor para uso direto
- **Conclusão**: SmolLM é a **tela em branco perfeita** para fine-tuning LoRA

---

## 2. Fases Concluídas

### ✅ Fase 1: Aquisição e Configuração
- [x] Download SmolLM2-135M-Instruct-Q4_K_M.gguf (105MB)
- [x] Validação de integridade (Magic: b'GGUF')
- [x] Perfil `BridgeConfig.smol_profile()` criado
- [x] Parâmetros otimizados: n_ctx=2048, threads=8, n_batch=512

### ✅ Fase 2: Pipeline de Dados
- [x] Dataset mínimo criado: `data/training/python_code.jsonl` (10 snippets Python em PT-BR)
- [x] `engine/training/dataset_loader.py` funcional
- [x] Validação de schema JSONL

### ✅ Fase 3: Orquestração de Treinamento
- [x] `engine/training/lora_trainer.py` com simulação validada
- [x] `engine/training/telemetry.py` gravando métricas em JSONL
- [x] `engine/training/__init__.py` criado
- [x] Adapter dummy gerado: `data/training/lora_adapter.bin`

### ✅ Fase 4: Integração e Validação
- [x] Teste de integração LoRA (modelo + adapter)
- [x] Inferência baseline validada (77 tok/s)
- [x] Pipeline completo operacional

---

## 3. Lições Aprendidas (Typhon Retrospective)

### 3.1 Performance vs Qualidade
- SmolLM é **3-5x mais rápido** que Qwen em CPU
- Mas **não segue instruções** em português sem fine-tuning
- Estratégia correta: usar SmolLM como base treinável, não como produto final

### 3.2 Arquitetura de Orquestração
- Pipeline `dataset_loader → lora_trainer → telemetry` é sólido
- Fallback de simulação permite testar fluxo sem backend real
- `BridgeConfig.smol_profile()` isola configuração de hardware

### 3.3 Próximos Gargalos
- **Treinamento LoRA REAL**: substituir simulação por backend real (CLI llama.cpp ou peft)
- **Dataset maior**: 10 snippets é insuficiente para treino real
- **Template de prompt**: SmolLM usa formato diferente do Qwen (ChatML)

---

## 4. Próximas Fases (Roadmap)

### 🟡 Fase 5: Treinamento LoRA Real
- [ ] Compilar `llama.cpp` com suporte a finetune
- [ ] Expandir dataset para 100-500 snippets Python
- [ ] Treinar adapter LoRA rank=4, lr=1e-4, 1 epoch
- [ ] Validar inferência com adapter carregado

### 🟡 Fase 6: Otimização de Peso
- [ ] Analisar dependências pesadas (llama-cpp-python, numpy, beautifulsoup4)
- [ ] Remover libs não utilizadas
- [ ] Compactar modelos e dados

### 🟡 Fase 7: Pacote de Treino Python
- [ ] Crawler especializado para docs.python.org
- [ ] Dataset estruturado de programação Python em PT-BR
- [ ] Pipeline de tokenização compatível com SmolLM

---

---

## 📋 BLITZPLAN: BRUNNR — Fase 5 (Treino Bilíngue + Boterminal)

**Protocolo**: ProDeNov v1.0 | **Data**: 2026-10-04  
**Hardware**: PC-B Bluebaby (i5-1235U, 16GB RAM)  
**Modelo Base**: SmolLM2-135M-Instruct → **Brunnr v0.1**  
**Status**: 🟢 Planejamento

---

### 1. Brainstorming e Análise de Viabilidade

#### 1.1 Pacote de Treino PT/EN
- **Objetivo**: Ensinar o Brunnr a responder fluentemente em português e inglês
- **Viabilidade**: **Alta**. O SmolLM já tem base em inglês; precisamos de ~500-2000 amostras PT/EN
- **Fontes offline** (sua preferência):
  - Dataset sintético expandido (funções Python com docstrings PT + EN)
  - Traduções de snippets do CodeAlpaca
  - Documentação Python traduzida (docs.python.org/pt-br/)
- **Formato**: JSONL com campo `lang` e pares `instruction_pt`/`instruction_en`

#### 1.2 Boterminal (Sistema de Comandos Controlados)
- **Objetivo**: Criar uma interface de terminal onde o Brunnr executa comandos controlados, não apenas responde perguntas
- **Conceito**: O Brunnr age como um **shell inteligente** — ele pode:
  - `brunnr.run("código python")` → executa e retorna output
  - `brunnr.explain("conceito")` → explica em PT ou EN
  - `brunnr.fix("arquivo.py")` → diagnostica e corrige
  - `brunnr.learn("novo dado")` → adiciona ao dataset de treino
- **Viabilidade**: **Média-Alta**. O ORN já tem `orn think`, `orn audit`, `orn fix`. O boterminal seria uma camada interativa sobre isso.
- **Risco**: Segurança de execução de código arbitrário → mitigado pelo sandbox existente (`code_sandbox.py`)

#### 1.3 Identidade do Brunnr
- **System Prompt**: `"Você é Brunnr, uma IA assistente de programação bilíngue (PT/EN). Responda sempre na mesma língua do usuário. Seja conciso e técnico."`
- **Personalidade**: Direto, técnico, bilíngue, focado em código

---

### 2. Tasklist e Checklist (Planos A, B, C)

#### Fase 5.1: Identidade Brunnr (Prioridade: Alta | Prazo: 30min)
- [ ] **5.1.1** Criar `docs/identity_brunnr.md` com system prompt e personalidade
  - *Plano A*: Documento markdown completo
  - *Plano B*: Inline no `BridgeConfig.brunnr_profile()`
- [ ] **5.1.2** Criar `BridgeConfig.brunnr_profile()` no `llm_bridge.py`
  - *Plano A*: Novo classmethod com system prompt do Brunnr + LoRA adapter
  - *Plano B*: Modificar `smol_profile()` existente

#### Fase 5.2: Pacote de Treino PT/EN (Prioridade: Alta | Prazo: 2 sessões)
- [ ] **5.2.1** Expandir dataset para 500+ amostras bilíngues
  - *Plano A*: Gerar sinteticamente pares PT/EN de funções Python
  - *Plano B*: Traduzir amostras do CodeAlpaca offline
  - *Plano C*: Crawler offline da docs.python.org/pt-br/
- [ ] **5.2.2** Criar `engine/tools/bilingual_dataset_builder.py`
  - *Plano A*: Script que gera JSONL com `{"text_pt": ..., "text_en": ..., "code": ...}`
  - *Plano B*: Adaptar `offline_dataset_processor.py` existente
- [ ] **5.2.3** Treinar adapter LoRA bilíngue (rank=8, epochs=2)
  - *Plano A*: `lora_trainer.py` com dataset expandido
  - *Plano B*: CLI do llama.cpp se PEFT falhar

#### Fase 5.3: Boterminal (Prioridade: Média | Prazo: 3 sessões)
- [ ] **5.3.1** Criar `engine/tools/brunnr_terminal.py`
  - *Plano A*: REPL interativo com comandos `run`, `explain`, `fix`, `learn`
  - *Plano B*: Integração com `orn think` existente via CLI
  - *Plano C*: Interface web via `engine/web/` existente
- [ ] **5.3.2** Sandbox de execução segura
  - *Plano A*: Reusar `code_sandbox.py` existente (`stage_code` + `python -I`)
  - *Plano B*: Subprocess isolado com timeout
- [ ] **5.3.3** Sistema de memória persistente (a "poça")
  - *Plano A*: JSONL append-only em `data/brunnr_memory.jsonl`
  - *Plano B*: SQLite leve via `engine/memory/vector_db.py`

#### Fase 5.4: Revisão de Regressão (Prioridade: Alta)
- [ ] **5.4.1** Validar que `orn think` ainda funciona com Qwen 0.5B
- [ ] **5.4.2** Validar que o adapter LoRA não quebra inferência base
- [ ] **5.4.3** Benchmark Brunnr vs SmolLM base vs Qwen

---

### 3. Placeholders (Esboço dos Arquivos)

#### `docs/identity_brunnr.md`
```markdown
# BRUNNR — Identidade da IA

**Codinome**: Brunnr (nórdico antigo: "poço, fonte, poça")
**Significado**: "Colocamos água (conhecimento) na poça, e ela se acumula."
**Versão**: 0.1 (SmolLM2-135M + LoRA PT/EN)
**Hardware**: PC-B Bluebaby (i5-1235U, CPU-only)

## System Prompt
"Você é Brunnr, uma IA assistente de programação bilíngue (PT/EN).
Responda sempre na mesma língua do usuário.
Seja conciso, técnico e direto.
Quando gerar código, inclua docstrings na língua do usuário.
Nunca invente APIs ou funções que não existem."

## Personalidade
- Direto e técnico (sem enrolação)
- Bilíngue (PT/EN, segue a língua do usuário)
- Focado em código (prioriza exemplos práticos)
- Honesto (diz quando não sabe)

## Comandos do Boterminal
- `brunnr> run <código>` — Executa código Python no sandbox
- `brunnr> explain <conceito>` — Explica conceito de programação
- `brunnr> fix <arquivo>` — Diagnostica e corrige arquivo
- `brunnr> learn <dado>` — Adiciona conhecimento à poça
- `brunnr> status` — Mostra estado do modelo e memória
- `brunnr> quit` — Encerra sessão
```

#### `engine/tools/brunnr_terminal.py`
```python
# RAIZ/engine/tools/brunnr_terminal.py
"""
Brunnr Terminal — Interface interativa de comandos controlados.
Objetivo: REPL inteligente onde o Brunnr executa, explica, corrige e aprende.
Typhon: onde=engine/tools/, oque=boterminal, quem=brunnr_terminal
quando=Fase 5.3, porquê=interface direta com a IA, origem=orn think + code_sandbox
consequência=se falhar, fallback para orn think via CLI.
"""
import sys
import time
from pathlib import Path
from typing import Callable

BRUNNR_BANNER = r"""
  ____                      _   _
 | __ ) _ __ _   _ _ __  _ __ | \ | |
 |  _ \| '__| | | | '_ \| '_ \|  \| |
 | |_) | |  | |_| | | | | | | | |\  |
 |____/|_|   \__,_|_| |_|_| |_|_| \_|
  v0.1 — SmolLM2-135M + LoRA PT/EN
  "Colocamos conhecimento na poça."
"""

COMMANDS = {
    "run":     "Executa código Python no sandbox",
    "explain": "Explica conceito de programação",
    "fix":     "Diagnostica e corrige arquivo Python",
    "learn":   "Adiciona conhecimento à poça (memória)",
    "status":  "Mostra estado do modelo e memória",
    "help":    "Lista comandos disponíveis",
    "quit":    "Encerra sessão",
}

class BrunnrTerminal:
    """REPL interativo com comandos controlados.
    
    Fluxo:
    1. Usuário digita comando
    2. Parser extrai ação + argumentos
    3. Dispatcher roteia para handler
    4. Handler executa (sandbox, LLM, memória)
    5. Output formatado no terminal
    
    Segurança:
    - 'run' usa sandbox isolado (python -I, timeout 5s)
    - 'fix' valida AST antes de sugerir patch
    - 'learn' append-only, sem execução
    """
    
    def __init__(self, bridge=None, validator=None):
        self._bridge = bridge
        self._validator = validator
        self._memory_path = Path("data/brunnr_memory.jsonl")
        self._running = False
    
    def start(self) -> None:
        """Inicia o REPL interativo."""
        print(BRUNNR_BANNER)
        print("Digite 'help' para ver comandos, 'quit' para sair.\n")
        self._running = True
        
        while self._running:
            try:
                user_input = input("brunnr> ").strip()
                if not user_input:
                    continue
                
                action, args = self._parse(user_input)
                self._dispatch(action, args)
                
            except KeyboardInterrupt:
                print("\n[INFO] Use 'quit' para sair.")
            except EOFError:
                break
        
        print("\n[INFO] Sessão encerrada. A poça mantém o conhecimento.")
    
    def _parse(self, text: str) -> tuple[str, str]:
        """Extrai ação e argumentos do input."""
        parts = text.split(maxsplit=1)
        action = parts[0].lower()
        args = parts[1] if len(parts) > 1 else ""
        return action, args
    
    def _dispatch(self, action: str, args: str) -> None:
        """Roteia comando para handler correto."""
        handlers = {
            "run":     self._cmd_run,
            "explain": self._cmd_explain,
            "fix":     self._cmd_fix,
            "learn":   self._cmd_learn,
            "status":  self._cmd_status,
            "help":    self._cmd_help,
            "quit":    self._cmd_quit,
            "exit":    self._cmd_quit,
        }
        
        handler = handlers.get(action)
        if handler is None:
            print(f"[ERRO] Comando desconhecido: '{action}'")
            print("       Digite 'help' para ver comandos disponíveis.")
            return
        
        handler(args)
    
    def _cmd_run(self, code: str) -> None:
        """Plano A: Executa código no sandbox isolado."""
        if not code.strip():
            print("[ERRO] Uso: run <código python>")
            return
        
        print(f"[INFO] Executando no sandbox...")
        t0 = time.perf_counter()
        
        try:
            from engine.tools.code_sandbox import stage_code
            import subprocess
            
            path = stage_code(code, stem="brunnr_run")
            result = subprocess.run(
                [sys.executable, "-I", str(path)],
                capture_output=True, text=True, timeout=5
            )
            
            elapsed = time.perf_counter() - t0
            
            if result.stdout:
                print(f"[OUTPUT]\n{result.stdout}")
            if result.stderr:
                print(f"[ERRO]\n{result.stderr}")
            if result.returncode == 0:
                print(f"[OK] Execução concluída em {elapsed:.2f}s")
            else:
                print(f"[FALHA] Código de retorno: {result.returncode}")
                
        except subprocess.TimeoutExpired:
            print("[ERRO] Timeout — possível loop infinito.")
        except Exception as e:
            print(f"[ERRO] {e}")
    
    def _cmd_explain(self, concept: str) -> None:
        """Plano A: Usa o LLM para explicar conceito."""
        if not concept.strip():
            print("[ERRO] Uso: explain <conceito>")
            return
        
        if self._bridge is None:
            print("[ERRO] Bridge não inicializado. Inicie com --model.")
            return
        
        prompt = f"Explique o conceito de '{concept}' em programação. Seja conciso e dê um exemplo prático."
        print(f"[INFO] Consultando Brunnr...")
        
        t0 = time.perf_counter()
        response = self._bridge.ask(prompt, max_tokens=256)
        elapsed = time.perf_counter() - t0
        
        print(f"\n{response}")
        print(f"\n[INFO] {elapsed:.2f}s")
    
    def _cmd_fix(self, filepath: str) -> None:
        """Plano A: Diagnostica arquivo e sugere correção."""
        if not filepath.strip():
            print("[ERRO] Uso: fix <arquivo.py>")
            return
        
        path = Path(filepath)
        if not path.exists():
            print(f"[ERRO] Arquivo não encontrado: {path}")
            return
        
        try:
            from engine.tools.code_sandbox import diagnose_python_file
            issues = diagnose_python_file(path)
            
            if not issues:
                print(f"[OK] {path.name} não tem problemas detectados.")
            else:
                print(f"[DIAG] {len(issues)} problema(s) encontrado(s):")
                for i, issue in enumerate(issues, 1):
                    print(f"  {i}. {issue}")
        except Exception as e:
            print(f"[ERRO] {e}")
    
    def _cmd_learn(self, data: str) -> None:
        """Plano A: Adiciona conhecimento à poça (append-only)."""
        if not data.strip():
            print("[ERRO] Uso: learn <conhecimento>")
            return
        
        import json
        self._memory_path.parent.mkdir(parents=True, exist_ok=True)
        
        entry = {
            "type": "user_knowledge",
            "content": data,
            "timestamp": time.time(),
        }
        
        with open(self._memory_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        
        print(f"[OK] Conhecimento adicionado à poça. ({self._memory_path})")
    
    def _cmd_status(self, args: str) -> None:
        """Mostra estado do modelo e memória."""
        print("[STATUS] Brunnr v0.1")
        print(f"  Modelo: SmolLM2-135M-Instruct + LoRA")
        print(f"  Bridge: {'ativo' if self._bridge else 'inativo'}")
        
        if self._memory_path.exists():
            lines = self._memory_path.read_text(encoding="utf-8").strip().split("\n")
            print(f"  Memória: {len(lines)} entradas na poça")
        else:
            print(f"  Memória: poça vazia")
    
    def _cmd_help(self, args: str) -> None:
        """Lista comandos disponíveis."""
        print("\n[COMANDOS]")
        for cmd, desc in COMMANDS.items():
            print(f"  {cmd:10s} — {desc}")
        print()
    
    def _cmd_quit(self, args: str) -> None:
        """Encerra sessão."""
        self._running = False

if __name__ == "__main__":
    terminal = BrunnrTerminal()
    terminal.start()
```

---

### 4. Questões Técnicas (Typhon)

| Pergunta | Resposta |
|---|---|
| **Onde?** | `engine/tools/brunnr_terminal.py`, `data/brunnr_memory.jsonl` |
| **O que?** | Boterminal REPL + pacote de treino bilíngue |
| **Quem?** | `BrunnrTerminal` (REPL), `lora_trainer.py` (treino) |
| **Quando?** | Fase 5 (após validação do LoRA) |
| **Quanto?** | ~500MB dataset, ~1h treino, ~2h implementação |
| **Por que?** | Transformar o SmolLM em assistente bilíngue interativo |
| **Origem?** | Decisão estratégica de criar IA própria com codinome Brunnr |
| **Consequência?** | Se falhar: fallback para `orn think` via CLI |

---

### 5. RIT (Roteiro de Implementação e Testagem)

#### Sessão 1: Identidade + Boterminal Básico (Hoje)
1. ✅ Criar `docs/identity_brunnr.md`
2. ✅ Criar `engine/tools/brunnr_terminal.py`
3. ✅ Testar REPL com `help`, `status`, `run`, `quit`
4. ✅ Testar `run "print('olá mundo')"` no sandbox

#### Sessão 2: Pacote PT/EN
1. ✅ Criar `engine/tools/bilingual_dataset_builder.py`
2. ✅ Gerar 500 amostras bilíngues
3. ✅ Treinar adapter LoRA bilíngue (rank=8)
4. ✅ Validar inferência PT e EN

#### Sessão 3: Integração Completa
1. ✅ Conectar boterminal ao LLM (`explain`, `fix`)
2. ✅ Implementar `learn` com memória persistente
3. ✅ Benchmark Brunnr vs base
4. ✅ Revisão de regressão

---

# 📊 Diagnóstico do Treino LoRA + Plano de Otimização

## 🔍 Análise dos Dados de Telemetria

### Métricas Reais (Epoch 1 — 500 steps)
| Métrica | Valor | Observação |
|---|---|---|
| **Loss inicial** | 9.0788 | Modelo base sem adaptação |
| **Loss final** | 0.3799 | Convergência excelente |
| **Loss médio** | 1.3814 | Aprendizado efetivo |
| **Tempo total** | ~44 min | 500 steps × ~5.3s/step |
| **Tempo/step (min)** | 660ms | Steps rápidos (batch pequeno) |
| **Tempo/step (max)** | 10,212ms | **15x mais lento** — GC/memory pressure |
| **Variação** | 660ms → 10s | Instabilidade severa |

### Problemas Identificados (Typhon)
1. **Batch size = 1**: Cada sample processado individualmente → overhead de forward/backward
2. **Sem gradient accumulation**: Perde oportunidade de simular batch maior
3. **Sem checkpointing**: Se travar no step 499, perde tudo
4. **Sem early stopping**: Continua treinando mesmo quando loss estabiliza
5. **GC spikes**: Picos de 10s indicam garbage collection do Python
6. **Bug no Boterminal**: `SiCDoxBridge.ask()` retorna string em vez de dict

---

## 🚀 Plano de Otimização Avançada (ProDeNov)

### 🎯 Objetivo
Reduzir tempo de treino de 44min → 15-20min (2-3x mais rápido) mantendo qualidade.

### Plano A: Batch Processing + Gradient Accumulation (Prioridade: Alta)

**O que é**: Processar múltiplos samples antes de atualizar pesos.

**Implementação**:
```python
# engine/training/lora_trainer.py — otimização
BATCH_SIZE = 4  # Processar 4 samples por vez
GRADIENT_ACCUMULATION_STEPS = 4  # Acumular gradientes de 4 batches

# Loop de treino otimizado
for epoch in range(epochs):
    optimizer.zero_grad()
    accumulated_loss = 0.0
    
    for i, batch in enumerate(dataloader):
        # Forward pass
        outputs = model(**batch)
        loss = outputs.loss / GRADIENT_ACCUMULATION_STEPS
        
        # Backward pass (acumula gradientes)
        loss.backward()
        accumulated_loss += loss.item()
        
        # Atualiza pesos a cada N steps
        if (i + 1) % GRADIENT_ACCUMULATION_STEPS == 0:
            optimizer.step()
            optimizer.zero_grad()
            
            # Log a cada batch completo
            if (i + 1) % (BATCH_SIZE * GRADIENT_ACCUMULATION_STEPS) == 0:
                avg_loss = accumulated_loss / GRADIENT_ACCUMULATION_STEPS
                log_step("STEP", f"Epoch {epoch+1}, Batch {i+1}, Loss: {avg_loss:.4f}")
                accumulated_loss = 0.0
```

**Ganho esperado**: 2-3x mais rápido (reduz overhead de forward/backward)

### Plano B: Mixed Precision (float16) (Prioridade: Média)

**O que é**: Usar float16 em vez de float32 para cálculos (metade da memória, 2x mais rápido).

**Implementação**:
```python
from torch.cuda.amp import autocast, GradScaler

scaler = GradScaler()

for batch in dataloader:
    optimizer.zero_grad()
    
    with autocast():  # Usa float16 automaticamente
        outputs = model(**batch)
        loss = outputs.loss
    
    scaler.scale(loss).backward()
    scaler.step(optimizer)
    scaler.update()
```

**Ganho esperado**: 1.5-2x mais rápido, 50% menos RAM

**Risco**: Pode causar overflow em gradients → usar GradScaler

### Plano C: Checkpointing + Early Stopping (Prioridade: Alta)

**O que é**: Salvar progresso periodicamente + parar quando loss não melhora.

**Implementação**:
```python
# Checkpoint a cada 50 steps
if step % 50 == 0:
    model.save_pretrained(f"data/training/checkpoint_step_{step}")
    log_step("CHECKPOINT", f"Salvo em step {step}")

# Early stopping
best_loss = float('inf')
patience = 100  # Parar se loss não melhorar em 100 steps
no_improve_count = 0

for step, batch in enumerate(dataloader):
    loss = train_step(batch)
    
    if loss < best_loss:
        best_loss = loss
        no_improve_count = 0
        model.save_pretrained("data/training/best_model")
    else:
        no_improve_count += 1
    
    if no_improve_count >= patience:
        log_step("EARLY_STOP", f"Parando em step {step} — loss não melhorou em {patience} steps")
        break
```

**Ganho esperado**: Evita treino desnecessário, salva progresso

---

## 📋 Roteiro de Execução (RIT)

### ATO 1: Documentação Consolidada
- [ ] Atualizar `docs/blitzplans/SmolLM_Infrastructure.md` com resultados reais
- [ ] Documentar métricas de treino (loss, tempo, convergência)
- [ ] Registrar lições aprendidas (Typhon retrospective)

### ATO 2: Análise de Peso do Sistema
- [ ] Executar `engine/tools/weight_analyzer.py`
- [ ] Identificar libs pesadas (torch, transformers, etc.)
- [ ] Criar relatório de otimização

### ATO 3: Pacote de Treino Python
- [ ] Expandir dataset para 1000+ samples
- [ ] Implementar crawler de docs.python.org
- [ ] Criar dataset estruturado (código + explicação PT/EN)

---

### Arquitetura Proposta: `doxoade shadow`

Vou propor um novo subsistema para o Doxoade que implementa exatamente isso:

```
doxoade/
├── tools/
│   └── shadow_systems/
│       ├── __init__.py
│       ├── shadow_manifest.py    # Rastreia original vs shadow
│       ├── shadow_provisioner.py # Copia e prepara o workspace
│       └── shadow_sync.py        # Sincroniza diffs upstream ↔ shadow
└── commands/
    └── shadow_cmd.py             # CLI: doxoade shadow {init,status,diff,sync}
```

### Comandos CLI

```bash
# Cria o shadow workspace a partir do projeto original
doxoade shadow init --source ../laurix_original --name laurix_shadow

# Mostra o status (o que foi modificado no shadow vs original)
doxoade shadow status

# Diff entre original e shadow
doxoade shadow diff

# Sincroniza mudanças do original para o shadow (merge upstream)
doxoade shadow sync --direction upstream

# Sincroniza mudanças do shadow para deploy
doxoade shadow deploy
```

### Estrutura de Diretórios

```
Laurix_proj/
├── laurix_original/          # Projeto do colega (INTACTO, read-only)
│   ├── core/
│   ├── include/
│   ├── kernel.c
│   ├── makefile
│   └── linker.ld
│
├── laurix_shadow/            # Sua cópia adaptada (MODIFICÁVEL)
│   ├── core/
│   ├── include/
│   ├── kernel.c
│   ├── makefile              # Pode ser substituído pelo Doxoade
│   ├── linker.ld
│   ├── laurix.toml           # Config do Doxoade Assembly Systems
│   └── .doxoade/
│       └── shadow_manifest.json  # Rastreia origem e modificações
│
└── laurix_deploy/            # Artefatos de produção (gerado)
    ├── bootloader.bin
    ├── kernel.bin
    └── os-image.bin
```

### `shadow_manifest.json` (Token Replacement)

```json
{
  "version": 1,
  "created_at": "2026-10-05T00:00:00",
  "source_project": "../laurix_original",
  "shadow_project": ".",
  "files": {
    "core/bootloader.asm": {
      "origin_hash": "sha256:abc123...",
      "shadow_hash": "sha256:def456...",
      "status": "modified",
      "modifications": [
        "ORG directive: removed brackets for NASM compatibility"
      ]
    },
    "core/kernel_entry.asm": {
      "origin_hash": "sha256:ghi789...",
      "shadow_hash": "sha256:ghi789...",
      "status": "unchanged"
    }
  },
  "token_replacements": [
    {
      "file": "core/bootloader.asm",
      "original": "[ORG 0x7C00]",
      "replacement": "ORG 0x7C00",
      "reason": "NASM flat binary syntax"
    }
  ]
}
```

### Vantagens desta Abordagem

| Aspecto | Sem Shadow | Com Shadow |
|---|---|---|
| **Original preservado** | ❌ Risco de corrupção | ✅ Intacto |
| **Rollback** | ❌ Manual/difícil | ✅ `shadow sync --direction upstream` |
| **Portabilidade** | ❌ Preso à sintaxe original | ✅ Adapta para NASM/GAS/FASM |
| **Deploy** | ❌ Misturado com fontes | ✅ Artefatos isolados |
| **Auditoria** | ❌ Sem rastreio | ✅ Manifest com hashes e diffs |

