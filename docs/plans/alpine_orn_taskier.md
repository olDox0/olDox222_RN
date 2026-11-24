# ORN Alpine Runtime — Taskier

**Data:** 2026-11-24  
**Status:** Backlog inicial — todas as tarefas ainda pendentes  
**Plano-mestre:** [alpine_orn_blitz.md](alpine_orn_blitz.md)

## Legenda

- [ ] Pendente
- [x] Concluída e verificada
- [~] Em andamento
- [!] Bloqueada / requer decisão técnica

Prioridades: **P0** bloqueia o avanço; **P1** necessária para o objetivo; **P2** melhoria posterior.

---

## Sprint A — Inventário e integridade

### T00 — Registrar o estado do Bluebaby [P0]
- [ ] Registrar modelo exato da CPU e instruções.
- [ ] Registrar Windows, QEMU e versão do executável `qemu-img`.
- [ ] Registrar RAM total/livre e espaço livre do volume de 125 GB.
- [ ] Registrar commit/branch do ORN usado no experimento.
- [ ] Registrar aceleração QEMU realmente disponível (WHPX/TCG).
- [ ] Salvar saída de `qemu-img info` do QCOW2 atual.

**Evidência:** inventário textual anexado ao registro do experimento.

### T01 — Auditar persistência real do Alpine [P0]
- [ ] Consultar `lsblk -f`, `df -h`, `mount` e `/etc/fstab`.
- [ ] Identificar disco, partição e filesystem realmente usados.
- [ ] Criar arquivo sentinela em local persistente.
- [ ] Reiniciar QEMU e confirmar que o sentinela continua presente.
- [ ] Se não houver persistência, planejar migração para instalação Alpine no QCOW2 antes da compilação do runtime.

**Arquivos de referência:** `engine/tools/qemu_daemon.py`, `engine/tools/disk_forge.py`, `docs/History/vol5_sandbox_web.md`.

**Critério:** dados de teste sobrevivem ao reboot; filesystem e dispositivo estão documentados.

### T02 — Backup e capacidade do QCOW2 [P0]
- [ ] Fazer cópia de segurança verificável da imagem atual.
- [ ] Confirmar espaço livre real no disco hospedeiro.
- [ ] Planejar imagem sparse com capacidade virtual de referência de 6 GiB.
- [ ] Verificar se o QCOW2 pode ser expandido sem recriação.
- [ ] Expandir a imagem, partição e filesystem de forma compatível com o filesystem encontrado.
- [ ] Confirmar capacidade e espaço livre dentro do Alpine.

**Arquivo-alvo de código:** `engine/tools/disk_forge.py`.

**Nota:** o DiskForge tem default de 512 MB. A expansão da imagem existente e o novo tamanho padrão para imagens futuras são tarefas distintas. Não formatar, apagar ou recriar a imagem existente.

**Critério:** espaço suficiente para toolchain, build, pacote ORN e GGUF; dados existentes preservados.

---

## Sprint B — Controle de recursos QEMU

### T03 — Tornar a RAM configurável [P0]
- [ ] Substituir o `-m 512M` fixo por configuração explícita.
- [ ] Usar variável de ambiente ou configuração equivalente, por exemplo `ORN_QEMU_RAM_MB`.
- [ ] Manter o default legado de 512 MiB quando não houver configuração.
- [ ] Configurar 1.280 MiB no perfil deste experimento.
- [ ] Validar tipo, faixa aceitável e erro de configuração inválida.
- [ ] Registrar a memória escolhida no log do daemon e na linha de comando QEMU.
- [ ] Testar que o perfil `code` continua com seus limites originais.

**Arquivo-alvo:** `engine/tools/qemu_daemon.py`.

**Critério:** sem variável, mantém comportamento legado; com 1280, o guest informa aproximadamente 1.280 MiB.

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

Executar apenas estes itens primeiro:

1. **T00:** inventário do Bluebaby e QEMU.
2. **T01:** confirmar persistência real do Alpine.
3. **T02:** backup, inspeção e expansão planejada do QCOW2.
4. **T03:** tornar a RAM configurável e usar 1.280 MiB no experimento.

Não iniciar build ou download do GGUF antes de T01/T02. Isso evita compilar e baixar o modelo em um filesystem volátil ou pequeno demais.

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
