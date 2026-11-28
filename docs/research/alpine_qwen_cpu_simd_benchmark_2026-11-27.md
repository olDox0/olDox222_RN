# EXP-010 — Backend CPU genérico vs. nativo no Alpine/QEMU

**Data:** 2026-11-27  
**Status:** benchmark comparativo concluído; backend nativo validado por smoke test  
**Projeto:** ORN / Alpine Runtime  
**Plano relacionado:** [alpine_orn_blitz.md](../plans/alpine_orn_blitz.md)  
**Taskier:** [alpine_orn_taskier.md](../plans/alpine_orn_taskier.md)

## 1. Objetivo

Medir o efeito prático de compilar `llama-cpp-python` para a arquitetura do processador hospedeiro e disponibilizar suas instruções ao Alpine através do QEMU. O experimento compara dois wheels da mesma versão do binding, no mesmo guest e com o mesmo modelo:

- backend genérico x86-64, sem extensões SIMD modernas;
- backend nativo, compilado com `-march=native` e `GGML_NATIVE=ON`.

O experimento mede o binding/modelo isoladamente. **Ainda não comprova a integração do ORN via `SiCDoxBridge.ask()`**.

## 2. Ambiente medido

### Hospedeiro e virtualização

| Item | Valor |
|---|---|
| Máquina de referência | Bluebaby |
| CPU hospedeira | Intel Core i5-1235U |
| Núcleos / threads lógicos do host | 10 / 12 |
| RAM visível no Windows | 15,69 GiB |
| Sistema hospedeiro | Windows 11 Pro, build 26300 |
| QEMU | 11.1.0 |
| Linha de comando relevante | `-accel whpx -accel tcg -cpu host,vmx=off -m 2048M -smp 2` |
| vCPUs do guest | 2 |
| RAM configurada | 2.048 MiB |
| RAM reconhecida no Alpine | `MemTotal: 2025356 kB` |
| RAM disponível na verificação após boot | `MemAvailable: 1864916 kB` |

A linha de comando oferece WHPX com TCG como alternativa. A escolha efetiva do acelerador não foi revalidada especificamente para esta rodada; não atribuir o resultado a um acelerador exclusivo sem nova evidência.

### Guest e toolchain

| Item | Valor |
|---|---|
| Distribuição | Alpine Linux 3.24.4, x86_64 |
| Kernel | 6.18.64-0-virt |
| libc | musl |
| Python | 3.14.10 |
| GCC / G++ | 15.2.0 |
| CMake | 4.2.3 |
| Ninja | 1.9 |
| llama-cpp-python | 0.3.38 |
| llama.cpp embutido | commit `f5e6915c28f10330885fcb9243a93ae98d3115ab` |

### CPU e instruções

A VM foi iniciada com `-cpu host,vmx=off`. O guest reportou, entre outras, as flags SSE4.2, AVX, AVX2, AVX-VNNI, FMA, F16C e BMI2.

Foi executado um pequeno programa C compilado com `-mavx2 -mfma -mf16c`. Resultados observados:

| Teste | Resultado |
|---|---:|
| Soma vetorial AVX2 | 116 |
| FMA | 4,0 |
| Conversão F16C | 1,0 |

O GCC também reportou como habilitadas por `-march=native`: `avx2`, `avxvnni`, `bmi2`, `f16c`, `fma` e `sse4.2`.

O binding nativo reportou:

```text
CPU : SSE3 = 1 | SSSE3 = 1 | AVX = 1 | AVX_VNNI = 1 | AVX2 = 1 |
F16C = 1 | FMA = 1 | BMI2 = 1 | LLAMAFILE = 1 | REPACK = 1 |
```

Essas verificações demonstram que as instruções testadas estão disponíveis e são executáveis no guest. Não demonstram, isoladamente, qual acelerador QEMU foi selecionado.

## 3. Modelo e integridade

| Campo | Valor |
|---|---|
| Modelo | Qwen2.5-Coder-0.5B-Instruct |
| Arquivo | `qwen2.5-coder-0.5b-instruct-q2_k.gguf` |
| Caminho no Alpine | `/opt/orn-models/qwen2.5-coder-0.5b-instruct-q2_k.gguf` |
| Quantização | Q2_K |
| Tamanho do arquivo | aproximadamente 390,28 MiB |
| SHA256 | `f9bddf294ef15c80bb64a2cdcf15d5b25caf88fb4f4a12383bc9f7a01a09c2e3` |
| Template de chat | `chat_template.default` |

O mesmo arquivo GGUF foi usado nos testes genérico e nativo.

## 4. Perfis de compilação

### 4.1 Wheel genérico

- Versão: `llama-cpp-python 0.3.38`.
- Perfil x86-64 genérico, sem AVX/AVX2/FMA/F16C/BMI2/SSE4.1/SSE4.2/SSSE3.
- `GGML_NATIVE=OFF`.
- OpenMP, BLAS e CUDA desligados.
- Wheel preservado em `/var/tmp/orn-wheelhouse`.
- SHA256: `9f418eea1780f232c162ef0bd5df9b4d8f993cb95ed33bda94e9a0af26b35d69`.

### 4.2 Wheel nativo

Flags e opções principais:

```text
CFLAGS=-O3 -march=native -mtune=native
CXXFLAGS=-O3 -march=native -mtune=native
GGML_NATIVE=ON
GGML_CPU_ALL_VARIANTS=OFF
GGML_OPENMP=OFF
GGML_BLAS=OFF
GGML_CUDA=OFF
CMAKE_BUILD_PARALLEL_LEVEL=1
```

- Wheel: `llama_cpp_python-0.3.38-py3-none-linux_x86_64.whl`.
- Tamanho: 32.651.283 bytes (aprox. 31,1 MB).
- SHA256: `d85d0ecfa4585a693d69f69b380735ff66b4d58ce91d93974dc4b9bfb9cb776d`.
- Build CMake persistente: `/var/tmp/orn-cmake-native`.
- Wheel extraído para `/var/tmp/orn-wheel-native-test`.

Os dois wheels foram testados via `PYTHONPATH`; **nenhum substituiu a instalação original do venv**. O wheel nativo carregou sem dependências ausentes e passou pela geração de texto com o Qwen.

## 5. Protocolo do benchmark comparativo

Parâmetros iguais nos dois backends:

| Parâmetro | Valor |
|---|---:|
| Contexto | 1.024 |
| Batch | 32 |
| Ubatch | 32 |
| Threads de geração | 2 |
| Threads de batch | 2 |
| Tokens máximos | 64 |
| Temperatura | 0 |
| Seed | 42 |
| mmap | ligado |
| mlock | desligado |
| OpenMP | desligado |
| Prompt | mesmo texto fixo nos dois testes; 50 tokens reportados |
| Formato | `chat_template.default` |
| Aquecimento | uma execução separada |
| Amostras medidas | 3 |

Métricas:

- **Prefill:** `n_p_eval / t_p_eval_ms`, via `llama_perf_context`.
- **Decode:** `n_eval / t_eval_ms`, via `llama_perf_context`.
- **Requisição:** tokens de conclusão divididos pelo tempo de parede da chamada.
- **RSS máximo:** `resource.getrusage(...).ru_maxrss`.

Todas as amostras medidas terminaram com `finish=length`, gerando 64 tokens.

## 6. Resultados — 2 threads

Velocidades em tokens/s; valores são médias de três execuções.

| Métrica | Genérico | Nativo | Razão nativo/genérico |
|---|---:|---:|---:|
| Prefill | 7,566 | **110,199** | **14,57×** |
| Decode | 6,511 | **35,961** | **5,52×** |
| Requisição | 3,920 | **28,461** | **7,26×** |

Medianas:

| Métrica | Genérico | Nativo |
|---|---:|---:|
| Prefill | 7,558 | 111,118 |
| Decode | 6,500 | 35,757 |
| Requisição | 3,915 | 28,384 |

Amostras individuais:

| Backend | Execução | Prefill | Decode | Requisição | Tempo de parede |
|---|---|---:|---:|---:|---:|
| Genérico | RUN 1 | 7,591 | 6,461 | 3,908 | 16,377 s |
| Genérico | RUN 2 | 7,558 | 6,500 | 3,915 | 16,347 s |
| Genérico | RUN 3 | 7,549 | 6,571 | 3,938 | 16,251 s |
| Nativo | RUN 1 | 107,037 | 36,817 | 28,818 | 2,221 s |
| Nativo | RUN 2 | 112,441 | 35,309 | 28,181 | 2,271 s |
| Nativo | RUN 3 | 111,118 | 35,757 | 28,384 | 2,255 s |

Tempo médio de parede por chamada: 16,325 s no genérico e 2,249 s no nativo, redução aproximada de 86,2%.

Pico de RSS observado:
- Genérico: 507,5 MiB.
- Nativo: 637,0 MiB.

## 7. Escalabilidade do backend nativo — 1 vs. 2 threads

O mesmo script e perfil nativo foram repetidos com uma thread:

| Métrica | 1 thread | 2 threads | Ganho com 2 threads |
|---|---:|---:|---:|
| Prefill | 85,358 | 110,199 | +29,1% |
| Decode | 25,263 | 35,961 | +42,3% |
| Requisição | 20,516 | 28,461 | +38,8% |

Pico de RSS: 635,9 MiB com 1 thread e 637,0 MiB com 2 threads.

A variação de decode nas três amostras de uma thread foi maior que nas amostras de duas threads; por isso, manter três ou mais repetições nas próximas rodadas.

## 8. Conclusão e limites

O perfil nativo apresentou ganho grande e reproduzível nas três amostras contra o perfil genérico, no ambiente e parâmetros registrados. A segunda thread também trouxe ganho relevante no perfil nativo.

Atribuição correta: o experimento compara **dois perfis completos de compilação**. O ganho não pode ser atribuído exclusivamente a AVX2 ou a uma única instrução: mudaram em conjunto o nível de otimização (`-O2` para `-O3`), alvo de arquitetura, instruções habilitadas e opções do GGML.

Limites:
- apenas um modelo Q2_K de 0,5B;
- prompt fixo de 50 tokens e saída de 64 tokens;
- três amostras por perfil;
- OpenMP desligado nos dois perfis;
- apenas duas vCPUs na VM;
- o acelerador QEMU efetivo não foi identificado novamente nesta rodada;
- a comparação foi entre wheels usados isoladamente via `PYTHONPATH`, não entre instalações definitivas;
- `SiCDoxBridge.ask()`, carga concorrente, contexto longo e estabilidade prolongada ainda não foram avaliados;
- não há comparação Windows/Alpine rigorosamente controlada com o mesmo commit/backend.

O wheel nativo é um artefato experimental específico para uma CPU compatível com as instruções expostas durante sua compilação. Não deve ser distribuído como binário genérico para CPUs sem as mesmas extensões.

## 9. Próximas etapas

1. Preservar os dois wheels e este registro.
2. Concluir a validação do ORN real no Alpine, incluindo `SiCDoxBridge.ask()`.
3. Repetir benchmark com mais amostras e, depois, testar 4 vCPUs como variável separada.
4. Comparar OpenMP desligado/ligado em uma experiência independente.
5. Tratar a GPU Iris Xe do Bluebaby como experimento posterior e separado; ver [plano da GPU](../plans/bluebaby_iris_xe_gpu_experiment_2026-11-27.md).

## 10. Artefatos e logs locais

Os itens abaixo foram gerados no guest e não devem ser adicionados ao Git:

- `/var/tmp/orn-wheelhouse/` — wheel genérico.
- `/var/tmp/orn-wheelhouse-native/` — wheel nativo.
- `/var/tmp/orn-wheel-test/` — extração do genérico.
- `/var/tmp/orn-wheel-native-test/` — extração do nativo.
- `/var/tmp/orn-cmake-native/` — build CMake persistente.
- `/var/tmp/orn-qwen-bench.py` — script usado nesta rodada.
- `/var/tmp/orn-qwen-generic-current.log` — resultado genérico.
- `/var/tmp/orn-qwen-native-current.log` — resultado nativo, 2 threads.
- `/var/tmp/orn-qwen-native-1thread.log` — resultado nativo, 1 thread.

O script de benchmark ainda não foi versionado. Para futuras comparações formais, deve ser incorporado ao repositório com parâmetros configuráveis e saída estruturada.
