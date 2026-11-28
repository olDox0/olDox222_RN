# ORN Alpine Runtime — Blitz Plan

**Data:** 2026-11-24  
**Status:** execução em andamento; backend CPU nativo medido no Alpine/QEMU; integração ORN ainda pendente  
**Repositório:** `olDox0/olDox222_RN`  
**Taskier:** [alpine_orn_taskier.md](alpine_orn_taskier.md)

## 1. Objetivo

Validar a portabilidade do ORN para Alpine Linux dentro do sandbox QEMU e investigar, por medição, se um ambiente Linux mínimo reduz o overhead do sistema e/ou melhora o desempenho percebido da inferência.

A hipótese não será tratada como conclusão antecipada:

- Alpine pode reduzir serviços e consumo de memória do sistema convidado.
- Isso não garante mais tokens/s: CPU, aceleração QEMU, compilação, bibliotecas, acesso ao GGUF, cache e paginação também influenciam.
- O experimento precisa separar custo do sistema operacional, custo da virtualização e diferenças entre backends.

**Resultado mínimo esperado:** o ORN deve carregar o Qwen no Alpine, executar `SiCDoxBridge.ask()` e manter uma sequência de requisições sem falhas.

## 2. Configuração de referência

| Item | Configuração |
|---|---|
| Máquina hospedeira | Bluebaby |
| RAM física | 16 GB (inventário: 15,69 GiB visíveis) |
| Disco/volume do repositório | C: com 15,69 GiB livres na coleta; capacidade do disco físico deve ser reconciliada com a especificação informada de 125 GB |
| CPU | Modelo exato a registrar no inventário |
| Hospedeiro | Windows + QEMU |
| Convidado | Alpine Linux x86_64 |
| RAM inicial do QEMU | 1.280 MiB |
| vCPU do QEMU | 2 |
| Aceleração | Registrar se WHPX ou TCG está efetivamente ativo |
| Modelo | Qwen2.5-Coder-0.5B-Instruct, GGUF Q4_K_M |
| Backend Python | llama-cpp-python compilado dentro do Alpine |
| Inferência inicial | CPU, 2 threads, contexto 1.024, lote 32, saída até 64 tokens |

A RAM de 1.280 MiB é o primeiro perfil de execução. Depois da prova funcional, o benchmark poderá comparar 1.280, 2.048 e 3.072 MiB, desde que a memória disponível no Bluebaby e a estabilidade do hospedeiro permitam.

O disco físico de 125 GB não significa que todo esse espaço esteja livre. O espaço livre do volume hospedeiro deve ser medido antes de expandir o QCOW2.

## 3. Estado conhecido do repositório

A inspeção do código atual identificou:

- `engine/tools/qemu_daemon.py`: inicialmente usava `-m 512M` fixo; T03 agora permite configurar a RAM pelo argumento `QemuDaemon(memory_mb=...)` ou pela variável `ORN_QEMU_RAM_MB`, preservando 512 MiB como default legado. O intervalo aceito é 256–8.192 MiB. Os 12 testes unitários passaram; a VM ainda foi iniciada com 512 MiB na coleta, então a validação de 1.280 MiB permanece pendente.
- Inventário do host em 2026-11-24: Intel Core i5-1235U (10C/12T), Windows 11 Pro build 26300, QEMU 11.1.0, 15,69 GiB de RAM visível e 7,92 GiB livres. Unidade C: tinha 15,69 GiB livres.
- QCOW2 atual: 2 GiB virtuais, ~353 MiB ocupados fisicamente, sem flag de corrupção. Isso contradiz o pressuposto de que a imagem existente teria apenas 512 MiB; o valor de 512 é default de criação, não tamanho constatado.
- A primeira execução do inventário do guest ocorreu com QEMU offline (PID antigo morto). O daemon iniciou depois com sucesso; o inventário do guest precisa ser repetido.
- `engine/tools/disk_forge.py`: `DiskForge.forge_qcow2()` cria discos novos com 512 MB por padrão.
- `engine/tools/qemu_daemon.py`: existe a constante `DISK_SIZE_MB = 512`; sua relação com o valor usado pelo DiskForge precisa ser consolidada.
- `engine/tools/sandbox_controller.py`: o método `run()` aplica limites por processo, inclusive `ulimit -v 262144`. Esse perfil é para execução de código e não deve ser reutilizado para inferência.
- `engine/core/llm_bridge.py`: `SiCDoxBridge` já possui fallback para `llama-cpp-python` quando o backend nativo não carrega. O caminho `native/orn.dll` é específico do ambiente Windows e precisa ser validado/isolado no Linux.
- `install.py`: contém flags e caminhos específicos de Windows/MinGW/w64devkit; não deve ser usado como instalador do Alpine.
- `pyproject.toml` declara uma dependência mínima de Click, enquanto `requirements.txt` também contém dependências de uso e inclui PyTorch. Não instalar todo o arquivo indiscriminadamente no primeiro boot.
- `docs/History/vol5_sandbox_web.md` registra uma pendência histórica sobre persistência do Alpine. A persistência atual precisa ser testada de ponta a ponta, não presumida.

## 4. Arquitetura-alvo do experimento

Na primeira etapa, o processo ORN será executado **dentro do Alpine**. O Windows/QEMU será responsável por hospedar e controlar o convidado. Não introduzir serviço remoto, HTTP ou nova camada de protocolo antes de provar a execução local no Alpine.

Fluxo:

```text
Bluebaby / Windows
    |
    +-- QemuDaemon / SandboxController
            |
            +-- QEMU (Alpine persistente)
                    |
                    +-- Python / pacote ORN
                    |       |
                    |       +-- SiCDoxBridge
                    |               |
                    |               +-- llama-cpp-python
                    |                       |
                    |                       +-- llama.cpp / CPU
                    |
                    +-- Qwen2.5-Coder-0.5B Q4_K_M
```

A interface pública `SiCDoxBridge.ask()` deve ser preservada. O primeiro objetivo de integração é fazer o backend Python carregar o GGUF no Linux. Uma API de inferência remota entre Windows e Alpine fica fora do escopo inicial.

## 5. Blitz por fases

### B0 — Inventário e linha de base

Registrar:
- commit do ORN usado no teste;
- modelo exato da CPU, instruções disponíveis e RAM livre do Bluebaby;
- versão do QEMU e backend de aceleração efetivo;
- versão e release do Alpine, kernel e arquitetura;
- tamanho virtual e tamanho físico do QCOW2, partições, filesystem e espaço livre;
- estado de persistência após reboot.

**Gate B0:** inventário salvo e cópia de segurança do QCOW2 existente.

### B1 — Infraestrutura persistente e dimensionável

- [x] Tornar a RAM do QEMU configurável por argumento ou variável de ambiente, preservando o default de 512 MiB.
- [x] Aplicar 1.280 MiB como valor configurável deste experimento (validação local ainda pendente).
- Confirmar que o convidado realmente recebe a RAM configurada.
- Inspecionar a imagem QCOW2 e o filesystem antes de expandir.
- Planejar disco virtual sparse de referência de 6 GiB, sujeito à confirmação do espaço livre no hospedeiro.
- Expandir a imagem existente de forma não destrutiva, preservando dados.
- Validar montagem, escrita, reboot e persistência de um arquivo sentinela.

**Gate B1:** Alpine inicia com recursos confirmados e mantém dados após reboot.

### B2 — Toolchain e ambiente Python

Instalar dentro do Alpine somente o necessário para o teste:
- build-base (GCC, G++ e ferramentas de build);
- CMake, Ninja e Git;
- Python, headers de desenvolvimento, pip e venv;
- linux-headers, pkgconf e certificados.

Não instalar PyTorch, CUDA, bibliotecas BLAS ou pacotes grandes sem evidência de necessidade. Mapear os imports reais do ORN e instalar dependências por etapa.

**Gate B2:** compilador, CMake, Python e venv validados.

### B3 — Backend nativo Python

Compilar `llama-cpp-python` dentro do Alpine, usando musl e toolchain local.

Perfil inicial conservador:
- CPU genérica (`GGML_NATIVE=OFF` até identificar as instruções expostas pelo QEMU);
- OpenMP inicialmente desligado;
- BLAS desligado;
- compilação serial (`CMAKE_BUILD_PARALLEL_LEVEL=1`);
- versão/tag/commit do llama-cpp-python e do llama.cpp registrados.

A integração Python será feita nesta mesma fase, conforme a configuração aprovada. O teste não será adiado para uma etapa posterior.

**Gate B3:** importação de `llama_cpp` e construção do objeto `Llama` sem falhas de biblioteca/ABI.

### B4 — Modelo e inferência mínima

- Disponibilizar o GGUF no disco persistente.
- Conferir nome, tamanho, metadados e SHA256.
- Carregar com `mmap=True`, `mlock=False`, CPU-only, 2 threads, contexto 1.024, lote 32.
- Gerar no máximo 64 tokens no teste inicial.
- Registrar tempo de carregamento, prompt eval, geração, tokens/s, RSS e eventos de OOM/paginação.

**Gate B4:** resposta válida em três execuções sequenciais e sem OOM.

### B5 — ORN no Alpine

- Disponibilizar o código do repositório dentro do convidado.
- Instalar o pacote ORN e dependências realmente necessárias, sem executar cegamente o instalador Windows.
- Validar imports dos módulos centrais.
- Executar `SiCDoxBridge.ask()` pelo backend `llama-cpp-python`.
- Executar um teste curto do caminho de CLI/serviço que representa o uso real pretendido.
- Corrigir incompatibilidades Linux em módulos específicos, sem reescrever a arquitetura.

**Gate B5:** ORN inicializa e realiza inferência pelo próprio bridge dentro do Alpine.

### B6 — Estabilidade e benchmark

Executar:
1. carregamento/descarregamento repetido;
2. dez execuções de inferência com prompts fixos;
3. vinte requisições sequenciais com o modelo residente;
4. teste de reinício do runtime e reboot do convidado.

Comparar:
- Windows com versão/backend llama.cpp equivalente;
- Alpine no QEMU;
- Alpine nativo, somente em fase futura.

Para isolar o efeito do SO, Windows e Alpine devem usar a mesma versão do llama.cpp/llama-cpp-python, o mesmo GGUF e parâmetros equivalentes. O backend `orn.dll` pode ser medido à parte, mas não deve ser usado como comparação direta de velocidade entre sistemas se o backend for diferente.

**Gate B6:** resultados reproduzíveis, parâmetros registrados e limitações documentadas.

## 6. Protocolo de benchmark

Cada execução deve registrar em JSON:
- identificador e data/hora;
- commit do ORN;
- SO, kernel, QEMU, aceleração e CPU exposta;
- RAM da VM, vCPU e memória livre do host;
- versão do llama-cpp-python/llama.cpp;
- SHA256 e tamanho do GGUF;
- `n_ctx`, `n_batch`, threads, mmap, mlock e max_tokens;
- load time, prompt eval, generation time, tokens/s, total latency e pico de RSS;
- resultado, erro, OOM e observações.

Usar prompts determinísticos e aquecimento separado. Reportar mediana, média e desvio padrão. Não misturar tempo de download/compilação com tempo de inferência.

## 7. Guardrails

1. Não alterar os limites do perfil `code` para acomodar o modelo.
2. Criar perfil separado de recursos para o runtime ORN.
3. Não apagar nem recriar o QCOW2 existente como atalho de expansão.
4. Fazer backup antes de operações de partição/filesystem.
5. Não assumir que WHPX está ativo só porque aparece na lista de argumentos; verificar o log e o comportamento do QEMU.
6. Não afirmar ganho de velocidade apenas porque Alpine usa menos RAM.
7. Não incluir modelo GGUF, wheels ou artefatos de build no Git.
8. Manter os resultados de benchmark separados do ambiente de produção.

## 8. Fora do escopo inicial

- Portabilidade do backend `orn.dll` para Linux.
- GPU, CUDA, Vulkan ou aceleração por dispositivo.
- Otimização avançada de quantização KV, Flash Attention ou OpenMP.
- Serviço remoto Windows↔Alpine.
- Alpine nativo fora do QEMU.
- Alterações no perfil de sandbox de execução de código.

Esses itens só entram após o Gate B5.

## 9. Critério de conclusão do Blitz

O Blitz será considerado concluído quando:
- Alpine persistente e com recursos configuráveis;
- `llama-cpp-python` compilado no próprio convidado;
- GGUF identificado por SHA256 e carregado;
- `SiCDoxBridge.ask()` funcionando no Alpine;
- vinte requisições sequenciais concluídas;
- benchmark Windows/QEMU documentado sem comparação enganosa;
- decisão fundamentada sobre continuar para Alpine nativo ou otimização do QEMU.

## 10. Atualização experimental — 2026-11-27

A fase de backend CPU avançou além do perfil genérico inicial. Foi construído e validado um wheel nativo `llama-cpp-python 0.3.38` com `-O3 -march=native -mtune=native` e `GGML_NATIVE=ON`. O QEMU foi iniciado com `-cpu host,vmx=off -m 2048M -smp 2`; o Alpine reconheceu aproximadamente 2 GiB e as instruções AVX2, AVX-VNNI, FMA, F16C e BMI2.

Benchmark comparativo com mesmo GGUF, prompt e parâmetros:
- Genérico (2 threads): 7,566 tok/s prefill; 6,511 decode; 3,920 requisição.
- Nativo (2 threads): 110,199 tok/s prefill; 35,961 decode; 28,461 requisição.

O wheel nativo também passou no smoke test de geração e no teste de dependências. Os resultados não fecham a integração do ORN: `SiCDoxBridge.ask()`, concorrência e estabilidade ainda precisam ser testados.

Relatório: [alpine_qwen_cpu_simd_benchmark_2026-11-27.md](../research/alpine_qwen_cpu_simd_benchmark_2026-11-27.md).

O experimento GPU continua fora do escopo do gate CPU atual, mas agora tem plano separado para execução posterior no Windows hospedeiro: [bluebaby_iris_xe_gpu_experiment_2026-11-27.md](bluebaby_iris_xe_gpu_experiment_2026-11-27.md). A VM QEMU atual não possui passthrough de GPU configurado.
