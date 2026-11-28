# ORN Alpine Runtime — Taskier

**Data:** 2026-11-27  
**Status:** Execução em andamento — T01, T03, T05 e T06 validadas; wheels genérico e nativo 0.3.38 compilados e testados isoladamente; benchmark CPU/SIMD concluído; integração `SiCDoxBridge.ask()` pendente; T17 (GPU Iris Xe) planejada para fase posterior  
**Plano-mestre:** [alpine_orn_blitz.md](alpine_orn_blitz.md)

## Legenda

- [ ] Pendente
- [x] Concluída e verificada
- [~] Em andamento
- [!] Bloqueada / requer decisão técnica

Prioridades: **P0** bloqueia o avanço; **P1** necessária para o objetivo; **P2** melhoria posterior.

---

## Sprint A — Inventário e integridade

### T00 — Registrar o estado do Bluebaby [P0] — parcial
- [x] Executar `scripts/alpine_orn_host_inventory.ps1`.
- [x] Registrar CPU: Intel Core i5-1235U, 10 cores / 12 threads; flags do host foram expostas e verificadas no guest após habilitar CPU host.
- [x] Registrar SO: Windows 11 Pro, build 26300.
- [x] Registrar QEMU: 11.1.0; executável em `C:\Program Files\qemu\`.
- [x] Registrar RAM: 15,69 GiB total, 7,92 GiB livres na coleta.
- [x] Registrar armazenamento da unidade C:: 15,69 GiB livres na coleta.
- [x] Registrar checkout: HEAD `b6b8746e8faa41e8c73b50013a93a9dea9139d65`.
- [x] Registrar QCOW2: 2 GiB virtuais, aproximadamente 353 MiB físicos, sem flag de corrupção.
- [x] Identificar aceleração efetiva como WHPX com evidência do módulo `WinHvPlatform.dll` carregado no processo QEMU.
- [ ] Confirmar flags de CPU disponíveis ao host e ao guest.

**Evidência:** `docs/plans/alpine_orn_inventory_2026-11-24.md`.

**Script:** `scripts/alpine_orn_host_inventory.ps1` (somente leitura).

### T01 — Auditar persistência real do Alpine [P0] — concluída
- [x] Registrar tentativa inicial de inventário com daemon offline (PID 11136 morto).
- [x] Reiniciar daemon com sucesso; estado reportado online, PID 10232.
- [x] Executar inventário com daemon online (PID 17260).
- [x] Identificar disco: `/dev/vda`, 2 GiB.
- [x] Identificar partições: `/dev/vda1` (~300 MiB, ext4 em `/boot`) e `/dev/vda2` (~1,75 GiB, ext4 em `/`).
- [x] Confirmar raiz em filesystem ext4 gravável, com ~1,2 GiB livres.
- [x] Validar o sentinela antes do reboot com `grep -qx ... && echo SENTINEL_OK`; retorno `SENTINEL_OK`.
- [x] Repetir a validação do sentinela após o reboot (PID 10936); retorno `SENTINEL_OK`.

**Evidência:** `docs/plans/alpine_orn_inventory_2026-11-24.md`. O arquivo `/workspace/.orn_alpine_persistence_probe` e o conteúdo `ORN_PERSIST_20261124` foram verificados antes e depois do reboot; a segunda verificação retornou `SENTINEL_OK`.
- [x] Migração por falta de persistência não é necessária: o sentinela sobreviveu ao reboot.

**Script:** `scripts/alpine_orn_guest_inventory.py` (somente leitura; não cria sentinela, não monta e não formata dispositivos).

**Arquivos de referência:** `engine/tools/qemu_daemon.py`, `engine/tools/disk_forge.py`, `docs/History/vol5_sandbox_web.md`.

**Critério atendido:** sentinela sobreviveu ao reboot; raiz identificada em `/dev/vda2` (ext4, RW), no QCOW2 de 2 GiB.

### T02 — Backup e capacidade do QCOW2 [P0] — backup verificado; expansão pendente de decisão
- [x] Registrar imagem atual: 2 GiB de tamanho virtual / ~353 MiB físicos.
- [x] Registrar espaço livre no volume do repositório: 15,69 GiB no momento da coleta.
- [x] Fazer cópia de segurança verificável da imagem atual em `data/sandbox/backups/alpine-before-orn-runtime-20261124.qcow2`.
- [x] Confirmar que nenhum processo `qemu-system-x86_64.exe` estava ativo antes da cópia.
- [x] Validar SHA256 idêntico na origem e na cópia: `b9c87ffa2bcff5ada49b993a96636d50d83fb1522cbce238e29bdf2407d17691`.
- [x] Confirmar espaço livre atual em C:: 94,05 GiB de 236,33 GiB (39,8%).
- [~] Reavaliar a necessidade de 6 GiB virtuais; imagem continua com 2 GiB e guest tem ~1,2 GiB livres.
- [x] Confirmar tabela MBR/DOS do disco virtual via `fdisk -l /dev/vda`.
- [x] Registrar `/dev/vda1`: início 2048, tamanho 614400 setores, fim 616447, tipo 83 Linux, bootável.
- [x] Registrar `/dev/vda2`: início 616448, tamanho 3577856 setores, fim 4194303, tipo 83 Linux; ext4 em `/`.
- [x] Confirmar `/dev/vda` em 2.097.152 KiB (2 GiB) e `blkid` para UUIDs das partições.
- [x] Confirmar que `e2fsck` existe; `resize2fs`, `sfdisk`, `growpart` e `lsblk` ainda ausentes.
- [x] Identificar `/sbin/fdisk` como applet BusyBox 1.37.0.
- [x] Simular `cloud-utils-growpart` e `e2fsprogs-extra`: 6 pacotes adicionais, incluindo `sfdisk 2.42.3-r1`, `partx`, `libfdisk`, `growpart` e `resize2fs`; APK reportou `OK: 562.2 MiB in 113 packages`.
- [x] Instalar `cloud-utils-growpart 0.33-r1` e `e2fsprogs-extra 1.47.4-r0`.
- [x] Confirmar `/usr/bin/growpart`, `/sbin/sfdisk` (util-linux 2.42.3) e `/usr/sbin/resize2fs`.
- [x] Confirmar `sfdisk -d /dev/vda`: label DOS, vda1 start 2048 size 614400; vda2 start 616448 size 3577856.
- [x] Confirmar raiz com 907,9 MiB disponíveis após instalação dos utilitários.
- [ ] Parar daemon, confirmar ausência de processo QEMU e fazer segundo backup do estado atual.
- [ ] Comparar SHA256 de origem e segundo backup.
- [ ] Redimensionar QCOW2 para 4 GiB e confirmar com `qemu-img info`.
- [ ] Executar `growpart /dev/vda 2`, confirmar start LBA 616448.
- [ ] Executar `resize2fs /dev/vda2` e confirmar novo espaço com `df -h /`.
- [ ] Criar segundo backup verificável do estado atual (toolchain + venv) com QEMU parado.
- [ ] Crescer o QCOW2 de 2 para 4 GiB sem shrink e sem sobrescrever backups.
- [ ] Crescer `/dev/vda2` preservando o setor inicial 616448; confirmar a nova tabela antes de alterar o filesystem.
- [ ] Expandir o ext4 de `/dev/vda2` e conferir `df -h /`.

**Arquivo-alvo de código:** `engine/tools/disk_forge.py`.

**Nota:** o QCOW2 já existente tem 2 GiB virtuais, apesar do default de 512 MB em DiskForge/CLI para imagens novas. Não inferir tamanho virtual pela constante/default. A expansão da imagem existente e o novo tamanho padrão para imagens futuras são tarefas distintas. Não formatar, apagar ou recriar a imagem existente.

**Critério:** espaço suficiente para toolchain, build, pacote ORN e GGUF; dados existentes preservados.

---

## Sprint B — Controle de recursos QEMU

### T03 — Tornar a RAM configurável [P0] — implementação, testes e validação no guest concluídos
- [x] Substituir o `-m 512M` fixo por configuração explícita.
- [x] Usar `ORN_QEMU_RAM_MB` ou o argumento `QemuDaemon(memory_mb=...)`.
- [x] Manter o default legado de 512 MiB quando não houver configuração.
- [x] Validar intervalo de 256 a 8.192 MiB e rejeitar valores inválidos.
- [x] Registrar a memória escolhida no log do daemon e no comando QEMU.
- [x] Adicionar testes unitários para default, variável de ambiente, precedência, limites e entradas inválidas.
- [x] Executar no checkout local: `12 passed in 0.20s`.
- [x] Reiniciar a VM com 1.280 MiB e confirmar `free -h` no Alpine.
- [ ] Confirmar que o perfil `code` continua com seus limites originais.

**Validação no Bluebaby em 2026-11-24:** no CMD, `set "ORN_QEMU_RAM_MB=1280"` foi seguido de `orn sandbox daemon restart`. O log registrou `guest RAM=1280 MiB` e `-m 1280M`; o guest reportou `Mem: 1.2G total`, aproximadamente 74,3 MiB usados e 1,0 GiB disponíveis. QEMU online, PID 10936, porta 8373.

**Arquivos:** `engine/tools/qemu_daemon.py`, `tests/test_qemu_memory_config.py`.

**Uso no PowerShell (nova instância do terminal):**
```powershell
$env:ORN_QEMU_RAM_MB = "1280"
orn sandbox daemon restart
```

**Critério:** sem variável, mantém comportamento legado; com 1280, o comando QEMU usa `-m 1280M` e o guest informa aproximadamente 1.280 MiB.

**Estado:** implementação, testes unitários e aplicação real de 1.280 MiB no Bluebaby concluídos.

### T04 — Consolidar a configuração do disco [P1]
- [ ] Resolver a duplicidade entre `DISK_SIZE_MB` no daemon e `size_mb=512` no DiskForge.
- [ ] Definir tamanho padrão para imagens novas, sem alterar automaticamente discos já existentes.
- [ ] Tornar explícito no log se a imagem existente foi reutilizada ou criada.
- [ ] Adicionar teste para criação, reutilização e preservação de imagem existente.

**Arquivos-alvo:** `engine/tools/disk_forge.py`, `engine/tools/qemu_daemon.py`.

### T05 — Verificar aceleração e CPU exposta [P0] — passthrough e ISA validados; acelerador do EXP-010 ainda a confirmar
- [x] Testar inicialização isolada de WHPX: retorno `WHPX_INIT_OK`.
- [x] Confirmar em rodada anterior que o processo QEMU carregou `WinHvPlatform.dll` (evidência de WHPX naquele processo/rodada).
- [x] Registrar CPU física do host: Intel Core i5-1235U, 10C/12T.
- [x] Registrar configuração do EXP-010: `-accel whpx -accel tcg -cpu host,vmx=off -m 2048M -smp 2`.
- [x] Confirmar no guest flags SSE4.2, AVX, AVX2, AVX-VNNI, FMA, F16C e BMI2.
- [x] Compilar e executar smoke test C com AVX2/FMA/F16C; resultados esperados foram obtidos.
- [x] Confirmar `llama_print_system_info()` do wheel nativo com AVX2, AVX-VNNI, FMA, F16C e BMI2 ativos.
- [ ] Confirmar qual acelerador (WHPX ou TCG) foi efetivamente selecionado durante o benchmark EXP-010.

**Nota histórica:** a CPU virtual genérica QEMU 2.5+ sem SSSE3/SSE4/AVX foi observada antes de definir `ORN_QEMU_CPU_MODEL=host,vmx=off`; não descreve o ambiente do EXP-010.

**Critério:** a aceleração e o conjunto de instruções usados no benchmark são conhecidos.

---

## Sprint C — Toolchain Alpine e Python

### T06 — Provisionar dependências de build [P0] — toolchain e venv validados; pacote llama-cpp permanece isolado por PYTHONPATH
Dentro do Alpine:
- [x] Confirmar Alpine 3.24.4, Python 3.14.10 e pip 26.1.2.
- [x] Confirmar GCC 15.2.0 e `musl-dev` instalados.
- [x] Simular os conjuntos APK completo (29 pacotes) e mínimo (17 pacotes).
- [x] Confirmar `/` e `/var/tmp` no mesmo ext4 persistente (`/dev/vda2`); `/tmp` é tmpfs.
- [x] Confirmar inodes: 5% usados, 106.028 livres antes da instalação.
- [x] Instalar `build-base cmake ninja git python3-dev linux-headers pkgconf ca-certificates` com `--no-cache`.
- [x] Verificar GCC/G++ 15.2.0, CMake 4.2.3, Ninja 1.9, Git 2.54.1, Python 3.14.10 e `python3-config --includes`.
- [x] Confirmar pós-instalação: 579,3 MiB usados, 999,7 MiB livres em `/` (37% ocupados).
- [x] Criar venv dedicado para o runtime em `/opt/orn-runtime/venv`.
- [x] Instalar dependências Python por wheels binários, sem cache e sem compilar dependências transitivas.
- [x] Instalar `numpy 2.5.5`, `scikit-build-core 1.1.2`, `typing-extensions 4.16.0`, `diskcache 5.6.3`, `jinja2 3.1.6`, `MarkupSafe 3.0.4`, `packaging 26.4` e `pathspec 1.1.1`.
- [x] Validar `pip check`: `No broken requirements found`.
- [x] Validar pacotes instalados: NumPy 2.5.5, scikit-build-core 1.1.2, typing-extensions 4.16.0, DiskCache 5.6.3 e Jinja2 3.1.6.
- [x] Medir o espaço após o venv: 670,0 MiB usados, 909,0 MiB livres em `/`.
- [x] Usar o Python do venv para executar o build CMake/scikit-build do wheel 0.3.38.
- [x] Validar importação de `llama_cpp` no wheel extraído via `PYTHONPATH`.
- [ ] Instalar o wheel selecionado dentro do venv depois de decidir o perfil padrão.

**Nota:** APK finalizou com `OK: 561.1 MiB in 107 packages`; esse valor é o total reportado do sistema, não o incremento isolado da instalação. Python foi atualizado de `3.14.10-r1` para `3.14.10-r2`.

### T07 — Mapear dependências reais do ORN [P1]
- [ ] Comparar `pyproject.toml`, `requirements.txt` e imports dos caminhos ORN que serão executados.
- [ ] Separar dependências obrigatórias de opcionais.
- [ ] Não instalar automaticamente `torch` no primeiro ciclo; justificar sua necessidade por módulo.
- [ ] Identificar dependências com extensões C/C++ ou disponibilidade limitada em musl.
- [ ] Preparar conjunto mínimo de dependências para o caminho `SiCDoxBridge.ask()`.

**Critério:** manifesto de dependências Linux sem pacotes pesados não utilizados.

### T08 — Compilar llama-cpp-python no Alpine [P0] — build genérico e nativo concluídos; instalação definitiva pendente
- [x] Fixar versão/tag do llama-cpp-python: `v0.3.38`.
- [x] Registrar o commit do llama.cpp embutido: `f5e6915c28f10330885fcb9243a93ae98d3115ab`.
- [x] Construir e preservar wheel genérico x86-64 com extensões SIMD modernas desativadas.
- [x] Construir wheel nativo com `-O3 -march=native -mtune=native` e `GGML_NATIVE=ON`.
- [x] Desligar OpenMP, BLAS e CUDA nos dois perfis comparados.
- [x] Compilar serialmente (`CMAKE_BUILD_PARALLEL_LEVEL=1`); o build nativo usou diretório CMake persistente em `/var/tmp/orn-cmake-native`.
- [x] Validar importação por `PYTHONPATH` e confirmar flags SIMD no backend nativo.
- [x] Resolver dependências do `libggml-cpu.so` e executar smoke test do Qwen no backend nativo.
- [ ] Instalar o wheel selecionado dentro de `/opt/orn-runtime/venv` após decisão de qual perfil será o runtime padrão.

**Critério parcial atendido:** ambos os wheels carregam em Alpine/musl sem dependências ausentes; a instalação definitiva no venv permanece deliberadamente separada.

---

## Sprint D — Modelo e inferência

### T09 — Disponibilizar e identificar o GGUF [P0] — modelo Q2_K usado no EXP-010; Q4_K_M continua pendente
- [x] Disponibilizar Qwen2.5-Coder-0.5B-Instruct Q2_K em `/opt/orn-models`, fora do venv e do checkout Git.
- [x] Registrar nome exato: `qwen2.5-coder-0.5b-instruct-q2_k.gguf`.
- [x] Registrar tamanho aproximado: 390,28 MiB.
- [x] Registrar SHA256: `f9bddf294ef15c80bb64a2cdcf15d5b25caf88fb4f4a12383bc9f7a01a09c2e3`.
- [x] Validar metadados e template `chat_template.default`; modelo carregou e gerou saída válida.
- [ ] Registrar/verificar a origem de distribuição do arquivo.
- [ ] Executar a matriz planejada com Q4_K_M, caso ainda seja necessária para o objetivo ORN.

**Critério parcial atendido:** GGUF Q2_K identificado por checksum, reconhecido pelo llama.cpp e utilizado no EXP-010.

### T10 — Criar teste de inferência mínima [P0] — smoke test e benchmark isolado concluídos
- [x] Criar script reproduzível temporário `/var/tmp/orn-qwen-bench.py` (ainda não versionado).
- [x] Configurar contexto 1.024, batch/ubatch 32, 2 threads, mmap ligado e mlock desligado.
- [x] Limitar cada geração a 64 tokens; usar temperatura 0 e seed 42.
- [x] Separar aquecimento de três amostras medidas por backend.
- [x] Registrar prompt/decode tokens/s, latência total e pico RSS.
- [x] Executar três amostras para os perfis genérico e nativo, além do nativo em uma thread, sem OOM.
- [ ] Versionar o script como ferramenta de benchmark e incluir saída JSON estruturada.
- [ ] Repetir em Q4_K_M se esse formato for escolhido para a validação final do ORN.

**Critério parcial atendido:** inferência isolada e benchmark controlado concluídos para Q2_K; integração ORN segue separada.

---

## Sprint E — ORN no convidado

### T11 — Disponibilizar o código ORN no Alpine [P1]
- [ ] Definir fluxo de sincronização do código para o convidado (clone da branch/commit ou mecanismo já existente).
- [ ] Fixar o commit exato usado nos testes.
- [ ] Instalar pacote ORN no venv em modo apropriado para desenvolvimento.
- [ ] Não copiar o venv Windows nem binários Windows para o convidado.
- [ ] Confirmar imports centrais e comandos de diagnóstico.

**Critério:** código do ORN disponível no Alpine e commit verificável.

### T12 — Validar o fallback Linux de SiCDoxBridge [P0]
- [ ] Confirmar que `native/orn.dll` não é carregado no Alpine.
- [ ] Verificar se o import de `NativeBackend` é seguro em Linux; proteger código estritamente Windows, caso necessário.
- [ ] Confirmar fallback para `llama-cpp-python`.
- [ ] Configurar caminho Linux do GGUF pelo mecanismo de configuração do ORN.
- [ ] Aplicar parâmetros de memória específicos do experimento sem mudar defaults globais.
- [ ] Executar `SiCDoxBridge.ask()` e `shutdown()`.

**Arquivo-alvo:** `engine/core/llm_bridge.py`.

**Critério:** inferência pelo bridge real dentro do Alpine, não apenas pelo teste isolado da biblioteca.

### T13 — Testar caminho de uso real [P1]
- [ ] Executar um comando CLI representativo.
- [ ] Executar uma segunda requisição sem recarregar o modelo desnecessariamente.
- [ ] Executar 20 requisições sequenciais.
- [ ] Registrar falhas, reloads, consumo de memória e latência.
- [ ] Corrigir somente incompatibilidades demonstradas.

**Critério:** 20 requisições concluídas sem falha e com comportamento de memória observado.

---

## Sprint F — Benchmark e conclusão

### T14 — Preparar benchmark controlado [P1] — comparação CPU parcial concluída
- [ ] Reutilizar/adaptar `tests/orn_llama_deep_profiler.py` ou versionar um script específico Alpine.
- [x] Fixar prompt, GGUF, versão do backend e parâmetros no EXP-010.
- [x] Separar warm-up das três amostras medidas.
- [x] Medir prefill, decode, velocidade da requisição, latência total e RSS.
- [ ] Emitir JSON com configuração completa e resultados.
- [x] Reportar média e mediana; desvio padrão ainda não incluído.

### T15 — Executar matriz comparativa [P1] — Alpine CPU genérico/nativo concluído parcialmente
- [ ] Windows com backend/versão equivalentes para comparação rigorosa.
- [ ] Repetir exatamente o mesmo script em 1.280 MiB se a comparação de RAM for relevante.
- [x] Alpine/QEMU com 2.048 MiB, 2 vCPUs e CPU host passthrough.
- [x] Comparar wheel genérico e nativo no mesmo guest, modelo, prompt e parâmetros.
- [ ] Testar 3.072 MiB somente se houver hipótese de memória a validar.
- [ ] Confirmar o acelerador efetivo (WHPX ou TCG) durante a rodada do benchmark.
- [ ] Manter `orn.dll` como comparação separada se não for o mesmo backend.
- [ ] Reservar Alpine nativo fora do QEMU para uma fase futura.

**Critério:** comparação reproduzível sem atribuir ao SO diferenças causadas pelo backend, CPU ou virtualização.

### T16 — Relatório e decisão [P1] — relatório preliminar EXP-010 registrado
- [x] Documentar ganhos e custo adicional de RSS dos perfis genérico/nativo.
- [x] Separar otimização de compilação/SIMD de alegações sobre desempenho do SO.
- [x] Registrar limitações do QEMU, backend e amostragem.
- [x] Definir continuação pela integração ORN no Alpine e teste posterior de vCPUs/OpenMP/GPU.
- [x] Atualizar o Blitz com resultados preliminares.
- [ ] Finalizar decisão global após validação do `SiCDoxBridge.ask()` e estabilidade prolongada.

**Critério:** decisão técnica sustentada pelos dados.

---

## Estado atual e próxima sequência — 2026-11-27

### Concluído e validado
- T01: persistência do Alpine comprovada por sentinela sobrevivente ao reboot.
- T03: RAM do QEMU configurável; perfis de 1.280 MiB e 2.048 MiB foram reconhecidos pelo guest em inicializações diferentes.
- T05: WHPX foi identificado em rodada anterior; passthrough `-cpu host,vmx=off` disponibilizou AVX2/FMA/F16C etc. nesta rodada. A aceleração efetiva WHPX/TCG ainda precisa ser anotada especificamente no benchmark EXP-010.
- T06: toolchain e venv dedicado disponíveis.
- T08: wheels genérico e nativo 0.3.38 compilados; wheel nativo validado via `PYTHONPATH`, sem substituir a instalação do venv.
- T09/T10: Qwen Q2_K identificado por SHA256, smoke test e benchmark concluídos isoladamente.
- T14/T15/T16: relatório comparativo CPU inicial produzido; a matriz Windows equivalente e dados estruturados permanecem pendentes.

### Próximas ações
1. **Prioridade P0 — T11/T12:** disponibilizar checkout fixo do ORN no Alpine, mapear dependências mínimas e validar `SiCDoxBridge.ask()`/`shutdown()` usando o backend Linux.
2. **T13:** executar caminho CLI representativo, requisições sequenciais e medir estabilidade/RSS.
3. **T14/T15:** versionar script de benchmark, adicionar saída JSON/desvio padrão e decidir se a comparação Windows 0.3.38 é necessária.
4. **Experimentos CPU seguintes:** testar 4 vCPUs e OpenMP em rodadas separadas; não misturar variáveis.
5. **T17 — GPU:** manter a Iris Xe como experimento posterior no Windows hospedeiro, depois da etapa CPU/ORN. A VM QEMU atual não possui passthrough de GPU.

### Armazenamento
O QCOW2 continua com 2 GiB virtuais. A expansão para 4 GiB é pendente de necessidade concreta e backup adicional; não é pré-requisito para o benchmark atual. Não alterar a partição M: `ALPINE` nem partições EFI/MSR/Recovery do host.
## Registro de decisões

| ID | Decisão | Estado |
|---|---|---|
| D01 | Host do estudo é Bluebaby, 16 GB RAM / 125 GB de disco | Aprovada |
| D02 | RAM inicial do QEMU: 1.280 MiB | Aprovada |
| D03 | Compilar llama-cpp-python dentro do Alpine | Aprovada |
| D04 | Integração Python ocorre na mesma fase do backend | Aprovada |
| D05 | Preservar o perfil restritivo `code` | Obrigatória |
| D06 | Persistência e capacidade de disco verificadas antes do build | Obrigatória |
| D07 | Manter backend Windows e Linux comparáveis antes de alegar ganho do SO | Obrigatória |

---

## Atualização experimental — 2026-11-27

### CPU/SIMD do Alpine/QEMU

- [x] QEMU reiniciado com `-cpu host,vmx=off -m 2048M -smp 2`.
- [x] Alpine confirmou `MemTotal: 2025356 kB`.
- [x] GCC `-march=native` reconheceu AVX2, AVX-VNNI, BMI2, F16C, FMA e SSE4.2.
- [x] Programa C executou AVX2, FMA e F16C com resultados esperados.
- [x] Wheel genérico `llama-cpp-python 0.3.38` preservado.
- [x] Wheel nativo 0.3.38 compilado serialmente, extraído separadamente e carregado via `PYTHONPATH`.
- [x] Smoke test do Qwen concluiu geração válida; dependências do `libggml-cpu.so` resolvidas.
- [x] Benchmark CPU genérico vs. nativo concluído em três execuções por perfil.
- [x] Benchmark nativo com uma thread concluído.

**Resultados e parâmetros completos:** [alpine_qwen_cpu_simd_benchmark_2026-11-27.md](../research/alpine_qwen_cpu_simd_benchmark_2026-11-27.md).

**Limite do gate:** o wheel nativo ainda foi testado isoladamente, fora da instalação principal do venv. A integração `SiCDoxBridge.ask()`, concorrência e estabilidade prolongada continuam pendentes. Portanto, T08/T10/T12 não devem ser consideradas integralmente fechadas apenas por estes testes.

### T17 — Avaliar Intel Iris Xe do Bluebaby via SYCL [P2] — planejado

- [ ] Fazer inventário do adaptador, PNP ID, driver e memória compartilhada no Windows.
- [ ] Confirmar enumeração da GPU via `sycl-ls` / Level Zero.
- [ ] Verificar compatibilidade de driver e Intel oneAPI antes da instalação.
- [ ] Construir llama.cpp com backend SYCL em ambiente separado no Windows hospedeiro.
- [ ] Testar o Qwen do EXP-010 com offload parcial e máximo.
- [ ] Comparar CPU e GPU no mesmo host, commit, GGUF, prompt e parâmetros.
- [ ] Registrar utilização, clocks, memória compartilhada, RSS, latência e tokens/s.
- [ ] Só depois avaliar integração no ORN.

**Observação de hardware:** o Intel Core i5-1235U é especificado com 80 Execution Units (EUs), frequência gráfica dinâmica máxima de 1,20 GHz e OpenCL 3.0. A ficha indica até 4 monitores suportados; esse número não representa quatro motores de computação. O driver informado pelo operador é `32.0.101.7088`; sua compatibilidade com o runtime oneAPI escolhido deve ser conferida na fase T17.

**Plano detalhado:** [bluebaby_iris_xe_gpu_experiment_2026-11-27.md](bluebaby_iris_xe_gpu_experiment_2026-11-27.md).

T17 é posterior à conclusão da validação do ORN/SiCDoxBridge no Alpine. O QEMU atual não tem passthrough de GPU configurado; o primeiro ensaio SYCL deve ser no Windows hospedeiro.
