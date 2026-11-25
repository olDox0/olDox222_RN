# Benchmark ORN — Qwen2.5-Coder no Windows e Alpine/QEMU

Data: 25/11/2026  
Projeto: `olDox0/olDox222_RN`  
Branch: `linux-alpine-sicdox-bridge`

## Resumo executivo

O mesmo GGUF Qwen2.5-Coder-0.5B-Instruct Q2_K foi executado pelo `SiCDoxBridge` em Windows nativo e Alpine Linux dentro do QEMU. O SHA256 coincidiu nos dois ambientes.

Com o engine já inicializado, duas chamadas foram executadas na mesma instância, limpando o contexto antes de cada pergunta e desativando a memoização do ORN. Os tempos registrados foram:

- Alpine/QEMU: 15,364 s na primeira chamada e 7,627 s na segunda.
- Windows: 1,728 s na primeira chamada e 0,679 s na segunda.

O Windows foi aproximadamente 8,89× mais rápido na primeira chamada, 11,23× na segunda e 9,55× na soma das duas. Esta é uma diferença observada no conjunto de software/hardware utilizado, não uma medição isolada do custo de virtualização.

A principal ressalva: Alpine usou `llama-cpp-python 0.3.38` e Windows usou `0.3.36`. As capacidades ISA, flags de compilação e commits llama.cpp de ambos os bindings ainda não foram auditados de forma comparável.

## 1. Artefato do modelo

| Propriedade | Valor |
|---|---|
| Nome | `qwen2.5-coder-0.5b-instruct-q2_k.gguf` |
| Quantização | Q2_K |
| Caminho no host | `models/sicdox/qwen2.5-coder-0.5b-instruct-q2_k.gguf` |
| Caminho no Alpine | `/opt/orn-models/qwen2.5-coder-0.5b-instruct-q2_k.gguf` |
| Tamanho reportado na transferência | aproximadamente 395 MiB |
| SHA256 | `f9bddf294ef15c80bb64a2cdcf15d5b25caf88fb4f4a12383bc9f7a01a09c2e3` |

Hash no host, via `certutil`:

```text
f9bddf294ef15c80bb64a2cdcf15d5b25caf88fb4f4a12383bc9f7a01a09c2e3
```

Hash no guest, via `sha256sum`:

```text
f9bddf294ef15c80bb64a2cdcf15d5b25caf88fb4f4a12383bc9f7a01a09c2e3
```

Os arquivos são idênticos segundo SHA256.

## 2. Condições comuns do benchmark

O código de benchmark construiu um `BridgeConfig` com as opções:

| Parâmetro | Valor |
|---|---:|
| `n_ctx` | 512 |
| `active_window` | 192 |
| `n_batch` | 32 |
| `n_threads` | 2 |
| `n_threads_batch` | 2 |
| `n_gpu_layers` | 0 |
| `max_tokens` | 24 |
| `response_hard_limit` | 24 |
| `temperature` | 0.0 |
| `top_p` | 1.0 |
| `use_mmap` | True |
| `use_mlock` | False |
| `no_alloc` | False |
| `cont_batching` | False |
| `flash_attn` | False |
| `rope_freq_base` | None |
| `repetition_memo_enabled` | False |
| `ORN_NATIVE_BACKEND` | 0 |

Prompt usado nos dois ambientes:

```text
Em Python, escreva uma função soma(a, b) que retorne a+b. Forneça apenas código, sem explicação.
```

Fluxo do teste:

1. Criar `SiCDoxBridge(cfg)`.
2. Chamar `_ensure_loaded()` e medir separadamente `LOAD_SECONDS`.
3. Executar duas chamadas a `ask()` na mesma instância.
4. Executar `clear_context()` antes de cada chamada.
5. Manter memoização desativada, evitando que a segunda chamada retorne uma resposta armazenada.
6. Consultar `stats()` e executar `shutdown()`.

Os tempos RUN medem a latência end-to-end de `bridge.ask()`. Incluem o trabalho do wrapper e a chamada ao backend. Não são equivalentes a uma medição isolada do loop de geração do llama.cpp.

## 3. Ambientes

### Alpine/QEMU

| Item | Valor |
|---|---|
| SO | Alpine Linux 3.24.4 |
| Kernel | Linux 6.18.64-0-virt |
| Python | 3.14.10 |
| libc | musl |
| `llama-cpp-python` | 0.3.38 |
| Compilador | GCC/G++ 15.2.0 |
| CMake | 4.2.3 |
| Ninja | 1.13.2 real |
| RAM do guest | aproximadamente 1.280 MiB |
| CPUs virtuais | 2 |
| CPU virtual reportada | QEMU Virtual CPU 2.5+ |
| ISA observada | MMX, SSE, SSE2; sem SSSE3, SSE4.x ou AVX |

O binding foi compilado localmente em CPU-only, sem OpenMP, sem `GGML_NATIVE` e sem extensões acima do baseline SSE2. GPU offload estava desativado (`n_gpu_layers=0`).

### Windows

| Item | Valor |
|---|---|
| SO | Windows 11 10.0.26300-SP0 |
| Python | 3.12.4 |
| `llama-cpp-python` | 0.3.36 |
| CPU host | Intel Core i5-1235U |
| Hardware host | 10 cores / 12 threads, 16 GiB RAM |
| GPU offload | desativado (`n_gpu_layers=0`) |

O binding 0.3.36 já estava instalado no venv. O alvo de CPU e as flags exatas de compilação do wheel Windows não foram auditados nesta rodada.

## 4. Resultados medidos

### 4.1 Tempos registrados

| Medição | Alpine/QEMU | Windows |
|---|---:|---:|
| `LOAD_SECONDS` | 0,352 s | 0,743 s |
| `RUN 1` | 15,364 s | 1,728 s |
| `RUN 2` | 7,627 s | 0,679 s |
| Total RUN 1 + RUN 2 | 22,991 s | 2,407 s |

### 4.2 Razões calculadas

| Comparação | Razão Alpine / Windows |
|---|---:|
| Primeira chamada | 8,89× |
| Segunda chamada | 11,23× |
| Soma das duas chamadas | 9,55× |

A segunda chamada no Windows levou aproximadamente 91,1% menos tempo que no Alpine. A soma das duas chamadas no Windows levou aproximadamente 89,5% menos tempo.

A razão mede o tempo observado. Não prova, por si só, que a virtualização seja a única ou principal causa.

### 4.3 Aquecimento

O tempo caiu de 15,364 s para 7,627 s no Alpine (aproximadamente 50,4% de redução). No Windows caiu de 1,728 s para 0,679 s (aproximadamente 60,7% de redução).

Como `use_mmap=True`, a inicialização do objeto não implica que todos os pesos tenham sido efetivamente lidos para RAM. Page faults e I/O podem ser cobrados durante a primeira inferência; o cache de páginas torna a segunda chamada mais rápida.

O valor de `LOAD_SECONDS` não deve ser apresentado como tempo integral de leitura dos pesos.

### 4.4 Tokens e qualidade

O benchmark aquecido limitou cada execução a 24 tokens no total. A saída do modelo terminou cortada pelo limite. O script não imprimiu o `usage` do backend por chamada; portanto não se deve derivar tokens/s desses tempos sem confirmar o total efetivo de completion tokens.

As respostas continham o código da função, mas também texto extra/trechos incompletos. A instrução "apenas código" não foi obedecida integralmente. Isso é uma questão de qualidade/formatação e limite de geração, separada da medição de latência.

Medições exploratórias anteriores no Alpine, com `response_hard_limit=48`, registraram:

| Inferência exploratória | Completion tokens | Tempo | Throughput reportado |
|---|---:|---:|---:|
| Qwen | 48 | 32,427 s | 1,480 tok/s |
| Qwen | 48 | 37,228 s | 1,289 tok/s |

Esses resultados pertencem a outra configuração de limite e não são diretamente comparáveis ao benchmark aquecido com 24 tokens.

## 5. O que foi validado

- Arquivo GGUF idêntico nos dois sistemas.
- Mesmo prompt e os mesmos parâmetros principais do bridge.
- Backend Python do ORN funcional em Alpine.
- Qwen carregado e inferência executada nos dois sistemas.
- Duas chamadas sequenciais, com contexto limpo e memoização desativada, na mesma instância em cada ambiente.
- Ciclo de vida do modelo e `shutdown()` validados no Alpine e Windows.

## 6. Hipóteses ainda abertas

As causas potenciais devem ser separadas, não presumidas:

1. **Versões diferentes:** 0.3.38 no Alpine versus 0.3.36 no Windows.
2. **ISA/SIMD:** guest expõe somente SSE2; o alvo real do wheel Windows ainda não foi identificado.
3. **Virtualização e CPU:** modelo QEMU, aceleração efetiva (WHPX/TCG), número de vCPUs, agendamento e custos de VM.
4. **Memória/cache:** page faults, mmap, page cache, RSS/PSS, pressão de RAM e I/O da imagem QCOW2.
5. **Prompt evaluation versus token generation:** os tempos atuais agregam ambas as etapas.
6. **Overhead do ORN:** `ask()` inclui contexto, prompt building, telemetria e backend.

## 7. Plano de investigação

### A. CPU/ISA e backend

Em ambos os ambientes, recolher:

- CPU e contagem de CPUs visíveis;
- flags de instruções visíveis;
- `llama_print_system_info()` do binding;
- capacidades/identificação do backend;
- GPU offload e bibliotecas carregadas.

No QEMU, registrar também CPU model e modo de aceleração realmente usado. Não presumir WHPX apenas porque foi habilitado na configuração do host.

### B. Versão idêntica

Instalar/compilar `llama-cpp-python 0.3.38` no Windows em ambiente separado, sem substituir o venv atual até concluir a validação. Registrar o commit/versionamento de llama.cpp embutido em cada pacote.

### C. Separar backend de wrapper

Executar o mesmo prompt e parâmetros diretamente com `llama_cpp.Llama`, fora do ORN, depois com `SiCDoxBridge.ask()`. Comparar:

- prompt evaluation;
- token generation;
- total end-to-end;
- telemetria e overhead do bridge.

### D. Memória e I/O

Medir RSS/PSS e page faults do processo antes, durante e depois da primeira e segunda inferências; registrar memória livre/disponível do guest e host e atividade de disco. Não limpar caches do sistema antes da linha de base.

### E. Matriz de parâmetros

Após padronizar versões e coletar a linha de base, variar uma dimensão de cada vez:

| Caso | Threads | Batch |
|---|---:|---:|
| A | 1 | 32 |
| B | 2 | 32 |
| C | 2 | 16 |
| D | 2 | 64 |

Manter modelo, SHA, prompt, contexto, limite de geração, versão do backend e estado de cache controlados.

## Conclusão provisória

**Foi observada uma diferença de 9,55× no tempo agregado das duas inferências aquecidas, com o Windows mais rápido. A causa ainda não foi isolada.**

Não alterar flags de compilação, ISA, CPU virtual ou valores de batch/thread até terminar a coleta das informações da CPU, backend, versões e perfil de memória.
