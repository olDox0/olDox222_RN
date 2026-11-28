# ORN Alpine Runtime — Taskier

**Data:** 2026-11-24  
**Status:** Execução em andamento — T01, T03, T05 e T06 concluídas; venv validado; resize do QCOW2 preparado, expansão pendente  
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
- [x] Registrar CPU: Intel Core i5-1235U, 10 cores / 12 threads (flags de instruções ainda pendentes).
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

### T05 — Verificar aceleração e CPU exposta [P0] — concluída
- [x] Testar inicialização isolada de WHPX: retorno `WHPX_INIT_OK`.
- [x] Confirmar que o processo QEMU da VM (PID 16452) carrega `WinHvPlatform.dll`, além de o teste isolado WHPX ter passado; evidência de WHPX ativo no processo da VM.
- [x] Registrar comando QEMU com `-accel whpx -accel tcg`, `-smp 2` e RAM 1.280 MiB.
- [x] Registrar CPU virtual no guest: `QEMU Virtual CPU version 2.5+`, fabricante `GenuineIntel`, família 15, modelo 107, 2 CPUs lógicas expostas.
- [x] Registrar flags do guest: `mmx`, `sse`, `sse2`, `pni` (SSE3), entre outras flags genéricas; não aparecem `ssse3`, `sse4_1`, `sse4_2` ou `avx`.
- [x] Definir compilação genérica, sem `-march=native` e sem `GGML_NATIVE=ON`.
- [x] Registrar diferença entre CPU física do host (Intel Core i5-1235U) e CPU virtual genérica apresentada ao Alpine.

**Critério:** a aceleração e o conjunto de instruções usados no benchmark são conhecidos.

---

## Sprint C — Toolchain Alpine e Python

### T06 — Provisionar dependências de build [P0] — dependências APK instaladas; venv pendente
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
- [ ] Registrar importações e executar teste de CMake dentro do venv.

**Nota:** APK finalizou com `OK: 561.1 MiB in 107 packages`; esse valor é o total reportado do sistema, não o incremento isolado da instalação. Python foi atualizado de `3.14.10-r1` para `3.14.10-r2`.

### T07 — Mapear dependências reais do ORN [P1]
- [ ] Comparar `pyproject.toml`, `requirements.txt` e imports dos caminhos ORN que serão executados.
- [ ] Separar dependências obrigatórias de opcionais.
- [ ] Não instalar automaticamente `torch` no primeiro ciclo; justificar sua necessidade por módulo.
- [ ] Identificar dependências com extensões C/C++ ou disponibilidade limitada em musl.
- [ ] Preparar conjunto mínimo de dependências para o caminho `SiCDoxBridge.ask()`.

**Critério:** manifesto de dependências Linux sem pacotes pesados não utilizados.

### T08 — Compilar llama-cpp-python no Alpine [P0]
- [x] Fixar versão/tag do llama-cpp-python: `v0.3.38`.
- [ ] Registrar o commit do submódulo llama.cpp embutido no sdist/tag e validar versão.
- [ ] Começar com CPU baseline: `GGML_NATIVE=OFF` e desligar explicitamente `GGML_SSE42`, `GGML_AVX`, `GGML_AVX2`, `GGML_BMI2`, `GGML_FMA` e `GGML_F16C`.
- [ ] Desligar `LLAVA_BUILD`, OpenMP, BLAS, CUDA e exemplos/testes/server não necessários.
- [ ] Compilar com paralelismo 1 para limitar pico de RAM.
- [ ] Instalar dentro do venv.
- [ ] Validar importação e registrar versão/caminho do módulo.

**Critério:** extensão nativa carrega em Alpine/musl sem erros de linker ou ABI.

---

## Sprint D — Modelo e inferência

### T09 — Disponibilizar e identificar o GGUF [P0]
- [ ] Usar Qwen2.5-Coder-0.5B-Instruct Q4_K_M.
- [ ] Conferir o repositório de origem e o nome exato do arquivo.
- [ ] Baixar para diretório persistente fora do venv.
- [ ] Registrar tamanho, metadados e SHA256.
- [ ] Garantir que modelo e artefatos grandes não sejam adicionados ao Git.

**Critério:** arquivo completo, reconhecido pelo llama.cpp e identificado por checksum.

### T10 — Criar teste de inferência mínima [P0]
- [ ] Criar teste reproduzível para carregar o GGUF via `llama-cpp-python`.
- [ ] Configurar contexto 1.024, lote 32, 2 threads, CPU-only.
- [ ] Usar mmap habilitado e mlock desabilitado.
- [ ] Limitar a saída a 64 tokens.
- [ ] Registrar load time, prompt eval, generation time, tokens/s e RSS.
- [ ] Executar três vezes e confirmar ausência de OOM.

**Arquivo sugerido:** `tests/test_alpine_runtime.py`.

**Critério:** três execuções sequenciais com saída válida e sem encerramento por falta de memória.

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

### T14 — Preparar benchmark controlado [P1]
- [ ] Reutilizar/adaptar `tests/orn_llama_deep_profiler.py`.
- [ ] Fixar prompts, GGUF, versão do backend e parâmetros.
- [ ] Separar warm-up das amostras.
- [ ] Medir carga, prompt eval, geração, tokens/s, RSS, CPU e latência total.
- [ ] Emitir JSON com configuração completa e resultados.
- [ ] Reportar média, mediana e desvio padrão.

### T15 — Executar matriz comparativa [P1]
- [ ] Windows com backend/versão equivalentes.
- [ ] Alpine em QEMU com 1.280 MiB.
- [ ] Repetir Alpine com 2.048 MiB e 3.072 MiB, se estável e útil.
- [ ] Registrar aceleração QEMU para cada rodada.
- [ ] Manter `orn.dll` como comparação separada se não for o mesmo backend.
- [ ] Reservar Alpine nativo para uma fase futura.

**Critério:** comparação reproduzível sem atribuir ao SO diferenças causadas pelo backend, CPU ou virtualização.

### T16 — Relatório e decisão [P1]
- [ ] Documentar ganhos e regressões de portabilidade.
- [ ] Separar economia de RAM/overhead de ganho em tokens/s.
- [ ] Registrar limitações do QEMU/musl e trabalho necessário para Alpine nativo.
- [ ] Decidir entre: otimizar QEMU, melhorar o backend Linux ou planejar teste nativo.
- [ ] Atualizar o Blitz com os resultados finais.

**Critério:** decisão técnica sustentada pelos dados.

---

## Próxima sequência de execução

O host reportou 15,69 GiB livres em C: (236,33 GiB, cerca de 6,6% livres). `Get-Disk` identificou um único NVMe ADATA de 238,47 GiB. O mapa GPT indica: partição 1 System/EFI 0,10 GiB; partição 2 Reserved 0,02 GiB; partição 3 C: 236,33 GiB; partição 4 M: FAT32 com label `ALPINE`, 1,00 GiB; partição 5 Recovery, 1,03 GiB. Os volumes sem letra correspondem às partições pequenas do disco. **Não apagar nem formatar nenhuma partição.** Suspender downloads/builds grandes até recuperar espaço em C:; a expansão QCOW2 continua sem necessidade demonstrada.

O comando sentinela executou `printf TOKEN > file && cat file` sem newline no arquivo. O `QemuDaemon.shell()` acrescenta um marcador na saída e filtra a linha que contém o marcador; por isso o texto pode ser descartado apesar do comando ter sido executado. Validar com:
```cmd
python -c "from engine.tools.qemu_daemon import QemuDaemon; print(QemuDaemon().shell('test \"$(cat /workspace/.orn_alpine_persistence_probe)\" = ORN_PERSIST_20261124 && echo SENTINEL_OK || echo SENTINEL_MISSING'))"
```
O `echo` escreve uma linha terminada em newline, permitindo ao parser preservar o resultado.

### Estado atual e próxima sequência

T01 e T03 estão concluídas. A persistência do Alpine foi comprovada pela sobrevivência do sentinela ao reboot; a RAM de 1.280 MiB foi aplicada e reconhecida pelo guest.

1. **T02 / capacidade:** backup inicial SHA256 verificado; agora raiz do guest tem ~909 MiB livres. MBR confirmado: vda2 inicia no setor 616448 e termina no 4194303. Preparar `growpart`/`resize2fs`; fazer segundo backup depois de parar QEMU antes do resize 2→4 GiB.
2. **T05:** concluída. `WinHvPlatform.dll` foi encontrada no processo QEMU PID 16452; o guest expõe QEMU Virtual CPU 2.5+ com SSE/SSE2/SSE3, sem SSSE3/SSE4/AVX. Compilar para baseline genérico.
3. **Modelos locais:** Qwen2.5-Coder 0.5B Q2_K, 395,9 MiB, disponível para smoke test. SmolLM2 135M Q4_K_M, 100,6 MiB, disponível para teste rápido de carga; não comparar diretamente resultados de modelos diferentes.
4. **T06–T08:** depois de fechar capacidade e CPU, provisionar toolchain e compilar `llama-cpp-python` dentro do Alpine.

A coleta mais recente reportou C: com 94,05 GiB livres de 236,33 GiB (39,8% livres), portanto o bloqueio anterior de armazenamento foi resolvido. A partição M: de 1 GiB, label `ALPINE`, permanece sem finalidade confirmada; não alterar nem formatar partições.

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
