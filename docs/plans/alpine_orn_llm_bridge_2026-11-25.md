# ORN no Alpine/QEMU — validação do SiCDoxBridge

Data de consolidação: 25/11/2026  
Branch: `linux-alpine-sicdox-bridge`  
Commit-base desta documentação: `bfd81d81333674b27b9e1f718390d302a449db4e`

## Estado atual

A portabilidade funcional do caminho Python do `SiCDoxBridge` para Alpine Linux está demonstrada. O bridge carregou dois GGUFs, executou `ask()`, registrou estatísticas e liberou o modelo com `shutdown()`.

O benchmark prático Alpine/QEMU versus Windows também foi executado. Ele aponta uma diferença grande de latência, mas ainda não isola a causa: os bindings usados são de versões diferentes (`llama-cpp-python 0.3.38` no Alpine e `0.3.36` no Windows), e o alvo de CPU e o modo de execução também diferem.

Relatório de medições, condições e plano de investigação:
[`docs/reports/alpine_windows_qwen_benchmark_2026-11-25.md`](../reports/alpine_windows_qwen_benchmark_2026-11-25.md).

## 1. Ambiente Alpine/QEMU

Ambiente observado durante a validação:

- Alpine Linux 3.24.4, x86_64, com musl.
- Kernel reportado: `Linux 6.18.64-0-virt`.
- Python 3.14.10.
- GCC/G++ 15.2.0.
- CMake 4.2.3.
- Ninja 1.13.2 real em `/usr/lib/ninja-build/bin/ninja`.
- Guest configurado com aproximadamente 1.280 MiB de RAM e duas CPUs virtuais.
- CPU virtual genérica QEMU 2.5+, com MMX, SSE, SSE2; sem SSSE3, SSE4.x ou AVX expostos.
- Sistema de arquivos raiz observado em aproximadamente 3,6 GiB.

### 1.1 Compilação de dependências

O NumPy 2.5.5 foi recompilado no Alpine sem baseline/dispatch de CPU, com compilação serial:

```sh
python -m pip install --force-reinstall --no-binary=numpy --no-cache-dir numpy==2.5.5 \
  -Csetup-args=-Dcpu-baseline=none \
  -Csetup-args=-Dcpu-dispatch=none \
  -Ccompile-args=-j1
```

O `llama-cpp-python 0.3.38` foi compilado localmente com backend CPU. A configuração desativou `GGML_NATIVE`, OpenMP, GPU e extensões acima do baseline SSE2 (incluindo SSE4.x, AVX/AVX2, AVX-512, FMA e F16C). A compilação nativa terminou com 151/151 alvos.

Houve uma incompatibilidade no comando `ninja` inicialmente encontrado no PATH: ele apontava para Samurai/`samu`, que falhava com segfault ao ler o log de build. O pacote `ninja-build` forneceu o executável real em `/usr/lib/ninja-build/bin/ninja`; o CMake foi reconfigurado explicitamente para usar esse caminho.

A instalação Python do binding gerou e instalou o wheel localmente. Importação e versão foram verificadas:

```text
llama_cpp.__version__ = 0.3.38
```

Não houve uso de GPU. O caminho de inferência validado nesta fase é `llama-cpp-python`.

## 2. Modelos transferidos e integridade

### SmolLM2-135M-Instruct Q4_K_M

- Origem no host: `models/smolm_sys/SmolLM2-135M-Instruct-Q4_K_M.gguf`.
- Destino guest: `/opt/orn-models/SmolLM2-135M-Instruct-Q4_K_M.gguf`.
- Tamanho observado no host: aproximadamente 100,6 MiB.
- SHA256 nos dois ambientes: `ed5fa30c487b282ec156c29062f1222e5c20875a944ac98289dbd242e947f747`.

Foi usado como smoke test do backend, não como referência de qualidade. O modelo apresentou baixa aderência a instruções simples.

### Qwen2.5-Coder-0.5B-Instruct Q2_K

- Origem no host: `models/sicdox/qwen2.5-coder-0.5b-instruct-q2_k.gguf`.
- Destino guest: `/opt/orn-models/qwen2.5-coder-0.5b-instruct-q2_k.gguf`.
- Tamanho observado durante transferência: aproximadamente 395 MiB.
- SHA256 confirmado no host e no Alpine: `f9bddf294ef15c80bb64a2cdcf15d5b25caf88fb4f4a12383bc9f7a01a09c2e3`.

O hash coincidente confirma que o benchmark utilizou o mesmo arquivo GGUF nos dois sistemas.

## 3. Alterações de portabilidade no ORN

As alterações foram mantidas isoladas na branch de trabalho, sem atualizar `main`.

Em `engine/core/llm_bridge.py`:

- Normalização de `BridgeConfig.model_path` para `Path`, com expansão de `~`.
- Precedência de caminho explícito do construtor sobre variável de ambiente.
- Aplicação de `ORN_MODEL_PATH` quando o caminho padrão está em uso.
- Descoberta de biblioteca nativa por plataforma: `orn.dll`, `liborn.dylib`/`orn.dylib`, `liborn.so`/`orn.so`.
- `ORN_NATIVE_BACKEND=0` desativa a descoberta automática do backend nativo.
- Fallback para Python após falha ao carregar o backend nativo.
- `shutdown()` libera o backend Python ou nativo.
- `stats()` reconhece o backend nativo como carregado.

Em `pyproject.toml`, a dependência de inferência foi adicionada como extra opcional:

```toml
[project.optional-dependencies]
llm = [
    "llama-cpp-python>=0.3.38",
]
```

No Windows CMD, a instalação editável com extra exige aspas duplas:

```cmd
python -m pip install -e ".[llm]"
```

A tentativa de instalar o extra no Windows baixou o source do binding, mas a compilação falhou porque o CMake selecionou `NMake Makefiles` e não encontrou `nmake` nem compilador C/C++. A instalação editável do ORN sem dependências adicionais funcionou:

```cmd
python -m pip install --no-deps -e .
```

Isso não afeta a instalação funcional do binding no Alpine nem comprova incompatibilidade de `llama-cpp-python` com Windows.

## 4. Testes automatizados e transferência

No Windows, com Python 3.12.4 e pytest 9.2.0:

```text
tests/test_alpine_llm_bridge.py
tests/test_kv_cache_options.py

24 passed in 0.75s
```

Os testes cobriram:

- resolução de `ORN_MODEL_PATH`;
- precedência do caminho explicitamente passado;
- desativação do backend nativo com `ORN_NATIVE_BACKEND=0`;
- ciclo de vida e estado do backend nativo;
- continuação de geração quando `finish_reason=length`;
- limite total de tokens e conversão de prompt pré-tokenizado.

A branch de trabalho foi empacotada com `git archive`, servida por HTTP no host e extraída no guest em `/opt/orn-src`. O pacote não incluiu ambiente virtual, histórico Git ou arquivos GGUF.

### 4.1 Particularidade do console serial

O daemon reconhece o prompt serial em `localhost:~#`, mas não reconhece corretamente o prompt que inclui diretório, por exemplo `localhost:/opt/orn-src#`. Ao falhar no reconhecimento, o caminho de recuperação envia Ctrl+C e pode fechar a conexão.

Recuperação observada no host:

```python
import socket
s = socket.create_connection(("127.0.0.1", 8373), timeout=5)
s.sendall(b"cd ~\n")
s.close()
```

O uso de subshell evita deixar a sessão serial em outro diretório:

```sh
(cd /opt/orn-src && comando)
```

Esse comportamento pertence ao controle de console/daemon, não ao LLM.

## 5. Testes funcionais de inferência

### 5.1 SmolLM2 no Alpine

Com `llama-cpp-python 0.3.38`, `n_ctx=512`, `n_batch=32`, duas threads, mmap habilitado e GPU desativada:

- O bridge carregou o modelo.
- `ask()` retornou texto.
- Tempo medido para a chamada completa: 25,188 s.
- `stats()` apresentou `model_loaded=True`.
- Após `shutdown()`, `stats()` apresentou `model_loaded=False`.

A resposta foi semanticamente inadequada. O teste valida o caminho de execução, não a qualidade do SmolLM.

### 5.2 Qwen2.5-Coder-0.5B no Alpine

Com `n_ctx=512`, `active_window=192`, `n_batch=32`, duas threads, `max_tokens=24`, `response_hard_limit=48`, temperatura zero e memoização padrão:

- Uma chamada de `ask()` terminou em 37,815 s.
- O log registrou testes com 48 tokens de conclusão em 32,427 s (1,480 tok/s) e 37,228 s (1,289 tok/s).
- `stats()` confirmou o modelo carregado.
- `shutdown()` confirmou a liberação.

Essas medições são exploratórias e não devem ser misturadas ao benchmark aquecido padronizado abaixo: nelas o limite total de saída era 48 tokens.

### 5.3 Benchmark aquecido padronizado

Condições comuns:

| Parâmetro | Valor |
|---|---:|
| Modelo | Qwen2.5-Coder-0.5B-Instruct Q2_K |
| SHA256 | `f9bddf294ef15c80bb64a2cdcf15d5b25caf88fb4f4a12383bc9f7a01a09c2e3` |
| Contexto | 512 |
| Janela ativa | 192 |
| Batch | 32 |
| Threads | 2 |
| Threads de batch | 2 |
| GPU layers | 0 |
| Tokens por chamada | 24 |
| Limite total de saída | 24 |
| Temperatura | 0.0 |
| Top-p | 1.0 |
| mmap | habilitado |
| mlock | desabilitado |
| no_alloc | desabilitado |
| continuous batching | desabilitado |
| flash attention | desabilitado |
| RoPE freq base | None |
| Memoização ORN | desabilitada |
| Prompt | o mesmo pedido de gerar `soma(a, b)` em Python, apenas código |

Procedimento: carregar o bridge antes de cronometrar as inferências, executar duas chamadas na mesma instância, limpar o contexto antes de cada chamada e manter a memoização desativada. O tempo de cada `RUN` é a latência end-to-end de `bridge.ask()`, não um cronômetro puro de tokens no backend.

| Métrica | Alpine/QEMU | Windows nativo |
|---|---:|---:|
| Python | 3.14.10 | 3.12.4 |
| SO | Alpine Linux 3.24.4 | Windows 11 10.0.26300 |
| llama-cpp-python | 0.3.38 | 0.3.36 |
| Inicialização `_ensure_loaded()` | 0,352 s | 0,743 s |
| RUN 1 | 15,364 s | 1,728 s |
| RUN 2 | 7,627 s | 0,679 s |
| Soma RUN 1 + RUN 2 | 22,991 s | 2,407 s |

Razões calculadas a partir dos tempos observados:

- Primeira chamada: Alpine demorou aproximadamente 8,89× o Windows.
- Segunda chamada: Alpine demorou aproximadamente 11,23× o Windows.
- Soma das duas chamadas: Alpine demorou aproximadamente 9,55× o Windows.
- Na segunda chamada, o Windows reduziu o tempo em aproximadamente 91,1% em relação ao Alpine.

Correção aritmética importante: o percentual de redução da segunda chamada é 91,1%, não 89,1%. O valor de 89,5% corresponde à redução do tempo agregado das duas chamadas.

`LOAD_SECONDS` mede o tempo da inicialização do objeto/engine e configuração do modelo. Como `use_mmap=True`, não deve ser interpretado como leitura integral dos pesos para RAM: parte do trabalho de I/O e page faults pode ocorrer durante a inferência.

O benchmark não imprimiu uso de tokens de cada RUN. Por isso, não se calcula tokens/s a partir desses tempos sem verificar o usage efetivo. Os valores de 1,289–1,480 tok/s são de execuções exploratórias diferentes.

## 6. Interpretação e limites das conclusões

Conclusões comprovadas:

1. O caminho Python do `SiCDoxBridge` executa no Alpine.
2. O binding Linux compilado localmente carrega o Qwen GGUF e gera texto.
3. O modelo é liberado por `shutdown()`.
4. O mesmo arquivo GGUF foi utilizado em Alpine e Windows, com SHA256 coincidente.
5. No benchmark aquecido observado, o Windows foi significativamente mais rápido.

O que ainda não está comprovado:

- quanto da diferença decorre de virtualização/hipervisor;
- quanto decorre de ISA/SIMD disponível e do alvo de compilação;
- quanto decorre da diferença entre `llama-cpp-python 0.3.36` e `0.3.38` e dos respectivos commits llama.cpp;
- se a CPU virtual, o limite de duas vCPUs, o I/O do QCOW2 ou o agendamento do host estão limitando a inferência;
- o custo separado de prompt evaluation e token generation;
- consumo de RAM/PSS/RSS ao longo do carregamento e inferência;
- desempenho após padronizar as versões e auditar as informações de sistema dos backends.

O Windows usa a CPU física Intel Core i5-1235U. O guest apresenta CPU virtual genérica QEMU com MMX/SSE/SSE2 e sem SSSE3/SSE4/AVX. As duas execuções usaram duas threads de inferência, mas os alvos binários e os caminhos de execução não são equivalentes.

As saídas também foram cortadas pelo limite de 24 tokens e não obedeceram completamente à instrução de retornar apenas código. Isso é uma limitação de qualidade/formatação a investigar separadamente do desempenho do backend.

## 7. Plano de diagnóstico do gargalo

A próxima etapa deve ser experimental, com uma variável alterada por vez. Não modificar flags CMake, arquitetura de CPU, versão do binding ou parâmetros de batch antes de recolher a linha de base.

### Etapa A — identificar CPU e capacidades efetivas

Coletar nos dois ambientes:

- nome/modelo da CPU e contagem de cores/threads visíveis;
- flags de ISA expostas ao processo;
- informações de backend retornadas por `llama_print_system_info()`;
- confirmação de GPU offload desativado;
- linha de comando e aceleração do QEMU (WHPX/TCG e modelo de CPU efetivamente selecionado).

### Etapa B — padronizar o backend

Usar `llama-cpp-python 0.3.38` nos dois ambientes, verificando também a versão/commit do llama.cpp incorporado. No Windows, preparar uma compilação controlada, sem substituir a instalação atual até o teste estar pronto.

### Etapa C — separar o custo do ORN

Comparar, em cada ambiente e com o mesmo arquivo/configuração:

1. `llama_cpp.Llama` diretamente;
2. `SiCDoxBridge.ask()`;
3. tempos de prompt evaluation e geração, quando expostos pelo backend;
4. latência end-to-end, telemetria e quantidade efetiva de tokens.

Isso identificará se existe sobrecarga relevante no bridge ou se o gargalo está no backend/execução.

### Etapa D — medir memória e I/O

Registrar antes, durante e depois da inferência:

- RSS e, quando disponível, PSS do processo Python;
- memória disponível do guest e do host;
- page faults e estado de cache;
- tempo até primeira resposta, não apenas inicialização de mmap;
- atividade de disco/QCOW2.

Não zerar caches de página nem alterar swap durante a primeira rodada.

### Etapa E — matriz controlada de parâmetros

Somente depois de A–D, testar `n_threads` e `n_batch` separadamente. A matriz inicial proposta é:

| Caso | Threads | Batch |
|---|---:|---:|
| A | 1 | 32 |
| B | 2 | 32 |
| C | 2 | 16 |
| D | 2 | 64 |

Manter constantes modelo, prompt, contexto, quantização, versão do binding, memoização e número de tokens.

### Etapa F — comparação QEMU vs execução nativa

Depois de padronizar o backend, comparar o Windows nativo com o guest e, se viável, variar apenas a CPU/acceleration configuration do QEMU. Confirmar primeiro se o modo atual usa WHPX ou TCG efetivamente; não deduzir apenas pelo nome da CPU apresentada ao guest.

## 8. Critério para encerrar o diagnóstico

O gargalo só deve ser atribuído a uma causa quando:

- as versões e os artefatos do backend estiverem identificados;
- a informação de CPU/ISA estiver registrada;
- as medições distinguirem prompt evaluation, geração e overhead de ORN;
- memória e I/O tiverem sido observados durante a inferência;
- um experimento controlado reproduzir a diferença ao alterar uma variável isolada.

Até lá, registrar a conclusão como: **diferença de desempenho observada entre Windows nativo e Alpine/QEMU, causa ainda não isolada**.
