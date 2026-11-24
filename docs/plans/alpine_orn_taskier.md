# ORN Alpine Runtime — Taskier

**Data:** 2026-11-24  
**Status:** Execução em andamento — T01 e T03 concluídas; T00/T02/T05 ainda têm verificações pendentes  
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
- [ ] Identificar aceleração QEMU efetiva (WHPX/TCG).
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

### T02 — Backup e capacidade do QCOW2 [P0]
- [x] Registrar imagem atual: 2 GiB de tamanho virtual / ~353 MiB físicos.
- [x] Registrar espaço livre no volume do repositório: 15,69 GiB no momento da coleta.
- [ ] Fazer cópia de segurança verificável da imagem atual.
- [ ] Confirmar espaço livre real no disco hospedeiro de destino do backup.
- [ ] Reavaliar a necessidade de 6 GiB virtuais; não expandir por padrão.
- [ ] Verificar se o QCOW2 pode ser expandido sem recriação.
- [ ] Expandir a imagem, partição e filesystem de forma compatível com o filesystem encontrado.
- [ ] Confirmar capacidade e espaço livre dentro do Alpine.

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

### T05 — Verificar aceleração e CPU exposta [P0]
- [ ] Confirmar se o QEMU está usando WHPX ou TCG.
- [ ] Registrar fabricante, modelo e flags visíveis em `/proc/cpuinfo`.
- [ ] Registrar `-smp 2` e o modelo de CPU efetivo.
- [ ] Não habilitar `-march=native` nem `GGML_NATIVE=ON` até confirmar compatibilidade.
- [ ] Anotar qualquer diferença de CPU entre Windows e convidado.

**Critério:** a aceleração e o conjunto de instruções usados no benchmark são conhecidos.

---

## Sprint C — Toolchain Alpine e Python

### T06 — Provisionar dependências de build [P0]
Dentro do Alpine:
- [ ] Atualizar índices do APK.
- [ ] Instalar `build-base`, `cmake`, `ninja`, `git`.
- [ ] Instalar `python3`, `python3-dev`, `py3-pip`, `linux-headers`, `pkgconf` e certificados.
- [ ] Criar venv dedicado para o runtime.
- [ ] Registrar versões dos pacotes e ferramentas.

**Critério:** GCC/G++, CMake, Python e pip funcionam dentro do venv.

### T07 — Mapear dependências reais do ORN [P1]
- [ ] Comparar `pyproject.toml`, `requirements.txt` e imports dos caminhos ORN que serão executados.
- [ ] Separar dependências obrigatórias de opcionais.
- [ ] Não instalar automaticamente `torch` no primeiro ciclo; justificar sua necessidade por módulo.
- [ ] Identificar dependências com extensões C/C++ ou disponibilidade limitada em musl.
- [ ] Preparar conjunto mínimo de dependências para o caminho `SiCDoxBridge.ask()`.

**Critério:** manifesto de dependências Linux sem pacotes pesados não utilizados.

### T08 — Compilar llama-cpp-python no Alpine [P0]
- [ ] Fixar versão/tag do llama-cpp-python.
- [ ] Registrar a versão correspondente do llama.cpp.
- [ ] Começar com CPU genérica: `GGML_NATIVE=OFF`.
- [ ] Começar com OpenMP e BLAS desligados.
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

1. **T02 / armazenamento:** fazer avaliação segura do espaço disponível em C: e decidir se há folga para backup do QCOW2. Não expandir a imagem por enquanto: o disco virtual tem 2 GiB e o guest ainda reporta cerca de 1,2 GiB livres.
2. **T05:** identificar a aceleração QEMU realmente utilizada (WHPX ou TCG) e registrar as flags de CPU vistas no Alpine.
3. **T06–T08:** somente após resolver espaço de armazenamento, provisionar toolchain e compilar `llama-cpp-python` dentro do Alpine.

O host tem 15,69 GiB livres em C: (236,33 GiB, cerca de 6,6% livres). A partição M: de 1 GiB, label `ALPINE`, permanece sem finalidade confirmada; não alterar nem formatar partições. Não iniciar downloads/builds grandes até avaliar e recuperar folga no C:.

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
