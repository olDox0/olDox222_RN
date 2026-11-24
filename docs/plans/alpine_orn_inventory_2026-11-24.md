# ORN Alpine Runtime — Inventário inicial do hospedeiro

**Coletado em:** 2026-11-24 01:21 (-03:00)  
**Origem:** saída de `scripts/alpine_orn_host_inventory.ps1` colada na conversa  
**Checkout:** `C:\Users\Victor Alexandre\Documents\ORN_proj`

## Hospedeiro

| Campo | Valor coletado |
|---|---|
| Equipamento | Dell Inspiron 15 3520 |
| CPU | Intel Core i5-1235U, 12ª geração |
| Núcleos / threads lógicos | 10 / 12 |
| Clock máximo reportado pelo CIM | 1.300 MHz |
| Sistema | Windows 11 Pro |
| Versão / build | 10.0.26300 / 26300 |
| RAM visível | 15,69 GiB |
| RAM livre na coleta | 7,92 GiB |
| Hipervisor detectado pelo Windows | True |
| QEMU | 11.1.0 (v11.1.0-12130-ge470268ff4) |
| Executável QEMU | `C:\Program Files\qemu\qemu-system-x86_64.exe` |
| Unidade C: livre na coleta | 15,69 GiB |
| Checkout HEAD | `b6b8746e8faa41e8c73b50013a93a9dea9139d65` |

**Atenção:** os 15,69 GiB livres são do volume C: que contém o checkout, não uma medição do espaço livre em todos os discos físicos. A capacidade física informada anteriormente como 125 GB deve ser reconciliada separadamente. O campo `HypervisorPresent=True` indica presença de hipervisor no host, mas não comprova isoladamente que esta execução QEMU usou WHPX.

## QCOW2 existente

| Campo | Valor |
|---|---:|
| Caminho | `data/sandbox/alpine.img.qcow2` |
| Formato | QCOW2 |
| Tamanho virtual | 2 GiB |
| Ocupação física | ~353 MiB |
| Cluster size | 65.536 bytes |
| Corrupt | false |

O tamanho virtual da imagem existente é 2 GiB. O valor de 512 MiB encontrado em `DISK_SIZE_MB` e em `DiskForge` é um default de criação e não descreve o tamanho atual deste arquivo.

## Estado do QEMU na coleta

O inventário inicial registrou logs históricos com invocações em 512 MiB. A primeira consulta ao guest terminou antes da inicialização e informou:

```text
QEMU status: offline (PID 11136 morto)
Guest inventory skipped: start the sandbox first.
```

Depois, o comando `orn sandbox daemon start` iniciou o convidado com sucesso. O log da inicialização registrou:

```text
guest RAM=512 MiB
QEMU ... -accel whpx -accel tcg -m 512M -smp 2 ...
Boot completo detectado.
Socket logado.
online (PID 10232, porta 8373)
```

Portanto, a implementação configurável de RAM ainda não foi aplicada ao processo QEMU desta coleta. A próxima validação deve executar o inventário do guest enquanto o daemon está online, antes de parar a VM.

## Testes já executados

```text
python -m pytest tests/test_qemu_memory_config.py -q
12 passed in 0.20s
```

Isso comprova os testes unitários de parsing/validação da configuração de memória, não a RAM efetiva vista pelo Alpine.

## Pendências

- [ ] Reexecutar `python scripts/alpine_orn_guest_inventory.py` com QEMU online.
- [ ] Confirmar disco/partição/filesystem, `mount`, `df -h` e `/etc/fstab`.
- [ ] Criar e validar sentinela de persistência após identificar o caminho persistente.
- [ ] Aplicar `ORN_QEMU_RAM_MB=1280`, reiniciar e conferir `free -h`.
- [ ] Confirmar aceleração WHPX ou TCG efetivamente utilizada.
- [ ] Medir as flags de CPU expostas pelo host e pelo guest.
- [ ] Fazer backup verificável do QCOW2 antes de qualquer expansão.


## Inventário do guest — 2026-11-24 (QEMU online)

O script `scripts/alpine_orn_guest_inventory.py` foi executado com o daemon online.

| Campo | Resultado |
|---|---|
| Estado QEMU | Online (PID 10232 na primeira coleta; PID 17260 após restart) |
| RAM configurada no boot | 512 MiB (ainda não alterada) |
| Memória reportada pelo guest | 468,1 MiB total; ~36,9 MiB usada na segunda coleta |
| Disco | `/dev/vda`, 2.097.152 setores de 512 bytes (~2 GiB) |
| Partição 1 | `/dev/vda1`, 307.200 setores (~150 MiB), ext4, montada em `/boot` |
| Partição 2 | `/dev/vda2`, 1.788.928 setores (~873 MiB em unidades de 512 bytes), ext4, montada em `/` |
| Raiz | `/dev/vda2`, ext4, RW |
| Espaço reportado em / | 1,6G total, ~302M usados, ~1,2G livres |
| Espaço em /boot | 271,1M total, ~27,8M usados |
| Swap | Não configurado |
| `/etc/fstab` | UUID do `/boot`; entrada do cdrom/usb e tmpfs; raiz não aparece explicitamente |

As unidades de tamanho apresentadas por `df` e `lsblk` podem diferir conforme arredondamento e blocos reservados. Não usar os números aproximados para operações de partição.

### Interpretação provisória

A raiz está em uma partição ext4 gravável de `/dev/vda`, e o daemon anexa o QCOW2 como dispositivo virtio. Isso é compatível com uma instalação persistente no disco virtual. **Persistência ainda não comprovada:** falta gravar um sentinela, parar/iniciar o QEMU e confirmar que o arquivo permanece.

### RAM — tentativa não aplicada

O prompt utilizado era CMD, mas foi digitada a sintaxe PowerShell `$env:ORN_QEMU_RAM_MB = "1280"`. CMD rejeitou a linha. O daemon reiniciou normalmente, porém o log confirmou `-m 512M`. Para CMD, utilizar:

```cmd
set "ORN_QEMU_RAM_MB=1280"
orn sandbox daemon restart
```

Depois confirmar no log `guest RAM=1280 MiB` e no Alpine com `free -h`.


## Atualização após retorno do usuário — 2026-11-24

### Resultado da tentativa do sentinela
O usuário executou:
```sh
mkdir -p /workspace && printf ORN_PERSIST_20261124 > /workspace/.orn_alpine_persistence_probe && cat /workspace/.orn_alpine_persistence_probe
```
A saída no host foi vazia. Interpretação técnica: `printf` criou o arquivo sem newline final; o `cat` também não emitiu newline. O método `QemuDaemon.shell()` acrescenta um marcador de término e remove linhas que contêm esse marcador. Assim, o token e o marcador podem ter ficado na mesma linha, fazendo o parser descartar a linha inteira. A ausência de saída não comprova falha de criação. Validar com:
```sh
test "$(cat /workspace/.orn_alpine_persistence_probe)" = ORN_PERSIST_20261124 && echo SENTINEL_OK || echo SENTINEL_MISSING
```

### Variável de RAM
No CMD, o usuário executou `set "ORN_QEMU_RAM_MB=1280"` e confirmou `echo %ORN_QEMU_RAM_MB%` = `1280`. Porém não foi executado `orn sandbox daemon restart` após definir a variável. A VM permanece com o boot registrado em 512 MiB até reinicialização.

### Armazenamento Windows
`Get-Volume` reportou:
- C: NTFS, 236,33 GiB total, 15,69 GiB livres (~6,6% livre).
- Volume sem letra NTFS: 1,03 GiB total, 0,10 GiB livre.
- M: FAT32: 1,00 GiB total, 0,97 GiB livre.
- Volume sem letra FAT32: 0,09 GiB total, 0,03 GiB livre.

O volume C: está com pouco espaço livre para uma compilação e instalação grandes. Os volumes sem letra e M: não foram identificados; não concluir que são partições dispensáveis. Suspender expansão do QCOW2 e operações de limpeza/partição até mapear `Get-Disk`, `Get-Partition`, labels e tipos de partição.

O usuário interrompeu as tentativas de `Get-Disk` por estar no CMD; o comando precisa ser chamado via `powershell -NoProfile -Command "..."`.


## Atualização do host e reboot — 2026-11-24 01:46 (-03:00)

### RAM aplicada e confirmada

No CMD foi definido `ORN_QEMU_RAM_MB=1280`, seguido de `orn sandbox daemon restart`. O daemon iniciou online com PID 10936 e porta 8373. O log confirmou `guest RAM=1280 MiB` e o comando `-m 1280M`. O inventário dentro do Alpine reportou `Mem: 1.2G total`, aproximadamente 74,3 MiB usados e 1,0 GiB disponíveis; swap continua em 0. Isso confirma que a configuração chegou ao processo QEMU e que o guest vê aproximadamente 1,2 GiB.

O comando de inicialização ainda contém `-accel whpx -accel tcg`; o log fornecido não identifica qual acelerador foi efetivamente selecionado.

### Persistência: teste parcial

Antes do restart, a verificação do arquivo `/workspace/.orn_alpine_persistence_probe` com `grep -qx ORN_PERSIST_20261124` retornou `SENTINEL_OK`. Isso comprova que o arquivo e o conteúdo existiam antes do reboot. Falta repetir o mesmo teste após o restart de PID 10936 para confirmar que o conteúdo sobreviveu ao ciclo de desligamento/inicialização.

Comando para a próxima verificação, executado no CMD:

```cmd
python -c "from engine.tools.qemu_daemon import QemuDaemon; print(QemuDaemon().shell('test -f /workspace/.orn_alpine_persistence_probe && grep -qx ORN_PERSIST_20261124 /workspace/.orn_alpine_persistence_probe && echo SENTINEL_OK || echo SENTINEL_MISSING'))"
```

### Inventário físico do armazenamento Windows

`Get-Disk` identificou um único disco: NVMe ADATA SM2P41C3 de 238,47 GiB (256 GB decimais), GPT. `Get-Partition` mostrou:

| Partição | Tipo / letra | Sistema / label | Capacidade |
|---|---|---|---:|
| 1 | System / sem letra | EFI | 0,10 GiB |
| 2 | Reserved / sem letra | MSR | 0,02 GiB |
| 3 | Basic / C: | NTFS | 236,33 GiB |
| 4 | Basic / M: | FAT32, label `ALPINE` | 1,00 GiB |
| 5 | Recovery / sem letra | NTFS | 1,03 GiB |

Volumes reportados: C: com 15,69 GiB livres; NTFS sem letra com 0,10 GiB livres; M: `ALPINE` com 0,97 GiB livres; FAT32 sem letra com 0,03 GiB livres. C: tem cerca de 6,6% livres. A antiga estimativa de 125 GB estava incorreta/incompleta: o disco é anunciado como 256 GB decimais, equivalentes a aproximadamente 238,47 GiB.

Não há evidência para apagar ou alterar as partições pequenas. M: é uma partição Basic interna rotulada `ALPINE`; preservar até identificar sua finalidade. Suspender downloads/builds grandes até investigar o uso de C: e recuperar folga. O QCOW2 atual permanece com 2 GiB virtuais e ~353 MiB físicos; a raiz Alpine usa ~302 MiB e tem ~1,2 GiB livres.


## Confirmação final de persistência — 2026-11-24 (após reboot PID 10936)

O usuário repetiu a verificação depois do `orn sandbox daemon restart` que iniciou o QEMU com 1.280 MiB. O comando verificou existência do arquivo e igualdade exata do conteúdo:

```cmd
python -c "from engine.tools.qemu_daemon import QemuDaemon; print(QemuDaemon().shell('test -f /workspace/.orn_alpine_persistence_probe && grep -qx ORN_PERSIST_20261124 /workspace/.orn_alpine_persistence_probe && echo SENTINEL_OK || echo SENTINEL_MISSING'))"
```

Saída observada: `SENTINEL_OK`.

**Conclusão:** o arquivo `/workspace/.orn_alpine_persistence_probe`, contendo exatamente `ORN_PERSIST_20261124`, sobreviveu ao reinício do QEMU. A persistência do sistema de arquivos do Alpine está comprovada para este ciclo de reboot. A raiz está montada em `/dev/vda2` como ext4 gravável e o QCOW2 associado ao QEMU tem 2 GiB virtuais. Não é necessária migração de instalação por falta de persistência.

Com isso, T01 está concluída. T03 também está validada: o daemon iniciou com `-m 1280M` e o Alpine reportou `Mem: 1.2G total`. Próximos pontos técnicos: investigar a folga de C: antes de downloads/builds, fazer backup verificável do QCOW2 se houver espaço e descobrir o acelerador QEMU efetivamente utilizado (WHPX ou TCG), além das flags de CPU visíveis no guest.


## Atualização posterior — armazenamento liberado e daemon offline

Em nova coleta via PowerShell, o volume C: passou a reportar 236,33 GiB totais, 94,05 GiB livres e 39,8% de espaço livre. Isso substitui a medição anterior de 15,69 GiB livres; a limitação de armazenamento para backup/builds deixa de ser o bloqueio imediato.

Na mesma rodada, `findstr` não encontrou referências a WHPX, TCG ou accelerator em `data/sandbox/qemu_daemon.log`. A ausência de texto nesse arquivo não identifica qual acelerador foi selecionado.

A tentativa de consultar `/proc/cpuinfo` não alcançou o guest: `QemuDaemon` reportou `offline (PID 10936 morto)`. Portanto, as flags de CPU do guest continuam pendentes. Próximo passo é iniciar o daemon novamente, confirmar que o boot continua com 1.280 MiB, e então repetir a coleta de CPU. Antes do backup do QCOW2, verificar também que não existe processo QEMU órfão ativo.


## Backup QCOW2 e teste WHPX — 2026-11-24 16:08 (-03:00)

Antes da cópia, `tasklist /FI "IMAGENAME eq qemu-system-x86_64.exe"` informou que não havia processo QEMU ativo. Foi copiada a imagem `data/sandbox/alpine.img.qcow2` para `data/sandbox/backups/alpine-before-orn-runtime-20261124.qcow2`.

Os dois comandos `certutil -hashfile ... SHA256` retornaram exatamente o mesmo SHA256:

`b9c87ffa2bcff5ada49b993a96636d50d83fb1522cbce238e29bdf2407d17691`

Conclusão: backup idêntico à imagem de origem, concluído com o QEMU desligado. A pasta `data/` está ignorada pelo `.gitignore`, portanto a imagem e o backup não devem entrar no versionamento normal.

Em seguida, um teste isolado QEMU com `-accel whpx -machine none -nodefaults -display none -S -monitor none` permaneceu ativo por 3 segundos e retornou `WHPX_INIT_OK`. Isso confirma que WHPX pode ser inicializado nesse host/QEMU. A VM Alpine foi iniciada depois com `-accel whpx -accel tcg -m 1280M -smp 2` e concluiu o boot (PID 16452). A documentação QEMU estabelece que, quando mais de um acelerador é passado, o seguinte só é usado se o anterior falhar na inicialização. Portanto WHPX é a seleção provável para o boot atual, mas a seleção no processo da VM ainda precisa de confirmação direta; o log `qemu_daemon.log` não mostrou mensagens de acelerador.

A primeira tentativa de ler `/proc/cpuinfo` falhou no CMD antes de alcançar o Python: aspas duplas dentro do argumento `python -c` encerraram a string e CMD interpretou `model` como comando. A VM estava online no PID 16452 após a sequência; repetir a leitura usando comando simples sem aspas internas, por exemplo `QemuDaemon().shell('cat /proc/cpuinfo | head -n 24')`.

### Modelos encontrados no host

A listagem `doxoade mk -t models\` mostrou, entre outros, `models/sicdox/qwen2.5-coder-0.5b-instruct-q2_k.gguf`, além de variantes SmolLM2 e Brunnr em diferentes quantizações. O Qwen local é Q2_K, diferente do Q4_K_M definido inicialmente no plano. Pode ser usado como modelo de smoke test, sem substituir silenciosamente o alvo Q4_K_M de benchmark. Tamanho exato dos GGUF ainda não foi coletado.


## CPU virtual e WHPX — resultado final de T05

Em 2026-11-24, com o guest online no PID QEMU 16452, o comando `Get-Process -Id 16452 -Module` retornou `WinHvPlatform.dll` em `C:\WINDOWS\SYSTEM32\WinHvPlatform.dll`. O teste isolado de inicialização com `-accel whpx` também retornou `WHPX_INIT_OK`. A linha de comando da VM registrou `-accel whpx -accel tcg`. Em conjunto, essas evidências indicam que o backend WHPX está efetivamente carregado no processo da VM, com TCG como fallback configurado.

A leitura de `/proc/cpuinfo` no Alpine retornou:

```text
processor       : 0
vendor_id       : GenuineIntel
cpu family      : 15
model           : 107
model name      : QEMU Virtual CPU version 2.5+
stepping        : 1
cpu MHz         : 2495.999
siblings        : 2
cpu cores       : 2
flags           : fpu de pse tsc msr pae mce cx8 apic sep mtrr pge mca cmov pat pse36 clflush mmx fxsr sse sse2 ht syscall nx lm rep_good nopl xtopology cpuid tsc_known_freq pni cx16 x2apic hypervisor lahf_lm pti ibt
```

Interpretação: o host físico é Intel Core i5-1235U, mas o guest recebe um modelo genérico QEMU Virtual CPU 2.5+, com 2 CPUs lógicas. As flags incluem SSE, SSE2 e `pni` (SSE3), mas não incluem SSSE3, SSE4.1, SSE4.2 ou AVX. Para compilar llama.cpp/llama-cpp-python nesse guest, usar baseline genérico; não usar `-march=native`, AVX ou `GGML_NATIVE=ON` sem mudar a configuração CPU virtual e repetir a inspeção.

### Modelos GGUF locais

Inventário de tamanho no host:

| Arquivo | Tamanho |
|---|---:|
| `models/sicdox/qwen2.5-coder-0.5b-instruct-q2_k.gguf` | 395,9 MiB |
| `models/smolm_sys/SmolLM2-135M-Instruct-Q4_K_M.gguf` | 100,6 MiB |
| `models/smolm_sys/smollm2-135m-instruct-q2_k.gguf` | 84,1 MiB |
| `models/smolm_sys/SmolLM2-135M-Instruct-f16.gguf` | 258,3 MiB |
| Variantes Brunnr Q4_K_M listadas | 100,6 MiB cada |

O Qwen 0.5B local é Q2_K, não o Q4_K_M inicialmente previsto. Ele pode ser o primeiro smoke test de integração com o modelo planejado. SmolLM2 135M Q4_K_M é menor e serve para verificar rapidamente carregamento e execução do backend, mas não é substituto comparável ao Qwen em benchmark de qualidade ou velocidade.

Com T05 concluída, a decisão de compilação é: CPU genérica, sem `GGML_NATIVE`, sem `-march=native`, build serial/paralelismo 1. O próximo passo é medir o espaço livre do guest e o estado atual das ferramentas antes de instalar pacotes APK.


## Inventário de toolchain e compatibilidade Python — 2026-11-24

Consulta de pacotes no Alpine 3.24.4:

| Pacote / comando | Estado |
|---|---|
| `gcc` | instalado — GCC 15.2.0 |
| `musl-dev` | instalado |
| `build-base` | meta-pacote ausente |
| `g++` | ausente |
| `cmake` | ausente |
| `ninja` | ausente |
| `git` | ausente |
| `python3` | instalado — Python 3.14.10 |
| `python3-dev` | ausente |
| `py3-pip` | instalado — pip 26.1.2 |
| `linux-headers` | ausente |
| `pkgconf` | ausente |
| `ca-certificates` | ausente |

Repositórios ativos: Alpine v3.24 main e community.

Verificação externa dos metadados da distribuição em 2026-11-24: PyPI lista `llama-cpp-python` 0.3.38, publicado em 2026-11-23, com classificador Python 3.14 e `Requires-Python >=3.8`. O sdist tem 79,4 MB e SHA256 `0570c9736b5e2a239b651da18687238eeba7fc2369dcdfd8cbb009dc1321e23f`. O `pyproject.toml` declara `scikit-build-core[pyproject]>=0.9.2` e CMake mínimo 3.21. Isto dá suporte de metadados à combinação Python 3.14, mas não substitui o teste de build nativo no Alpine/musl.

Próximo passo seguro: executar `apk add --simulate build-base cmake ninja git python3-dev linux-headers pkgconf ca-certificates` para inspecionar o plano e o espaço antes de instalar. Não compilar em `/tmp` porque o inventário anterior mostrou `/tmp` como tmpfs; usar diretório em disco ext4, como `/var/tmp/orn-build`, e limitar o paralelismo de CMake a 1.


## Simulação de dependências APK — T06.2

No Alpine 3.24.4, o usuário executou `apk add --simulate build-base cmake ninja git python3-dev linux-headers pkgconf ca-certificates`. A resolução foi concluída sem erro e listou 29 pacotes novos. Entre eles: `g++ 15.2.0-r5`, `make 4.4.1-r4`, `build-base 0.5-r4`, `cmake 4.2.3-r0`, `git 2.54.1-r0`, `linux-headers 7.0.0-r1`, `pkgconf 2.5.1-r0`, `python3-dev 3.14.10-r1`, `ca-certificates 20261020-r0` e `samurai 1.2-r8` (backend leve do tipo Ninja selecionado pela resolução).

A linha final foi `OK: 560.4 MiB in 106 packages`. Interpretação: tamanho/estado total reportado pelo APK para o conjunto simulado, não bytes de download e não a diferença de espaço que será consumida isoladamente. Antes da simulação, o guest reportava aproximadamente 1,2 GiB livres em `/`.

Para minimizar pressão de disco, a próxima etapa deve simular um conjunto mínimo: `build-base cmake python3-dev pkgconf ca-certificates`, sem `git`, `linux-headers` e `ninja` explícitos. Usar Make/Unix Makefiles no primeiro build. Confirmar `df -h / /var/tmp` e montagem de `/var/tmp` antes de transferir/extrair fontes; `/tmp` é tmpfs e não deve ser usado para os artefatos de compilação. Instalar por etapas e conferir espaço depois.


## Instalação efetiva da toolchain APK — T06 concluída

O usuário executou no guest `apk add --no-cache build-base cmake ninja git python3-dev linux-headers pkgconf ca-certificates`. A operação foi concluída sem erro, com `OK: 561.1 MiB in 107 packages`. O log mostrou 33 ações de instalação/upgrade, incluindo atualização de Python `3.14.10-r1` para `3.14.10-r2` e instalação de `python3-dev 3.14.10-r2`.

Verificação após instalação:

| Ferramenta / métrica | Resultado |
|---|---|
| GCC | Alpine 15.2.0 |
| G++ | Alpine 15.2.0 |
| CMake | 4.2.3 |
| Ninja | 1.9 |
| Git | 2.54.1 |
| Python | 3.14.10 |
| `python3-config --includes` | `-I/usr/include/python3.14` |
| Raiz `/` | 579,3 MiB usados; 999,7 MiB disponíveis; 37% usado |

Status: dependências de compilação instaladas. Próximo passo: criar venv dedicado em `/opt/orn-runtime/venv` e preparar build serial com controle de `TMPDIR` em `/var/tmp`.

### Relato separado: Barrier / Amaranth

O usuário relatou que a operação pareceu afetar o Amaranth enquanto utiliza Barrier, mas não descreveu o sintoma. A operação APK ocorreu no Alpine guest por meio de `QemuDaemon.shell()`; não há evidência atual de que tenha alterado configurações do Windows, do Barrier ou de outro computador. O screenshot enviado mostra o Lite XL com o arquivo `doxoade/tools/audio_systems/__init__.py` aberto, mas não exibe a interface/estado do Barrier. Não atribuir causalidade sem conhecer o efeito concreto (desconexão, lag, perda de teclado/mouse ou clipboard).



## Toolchain instalada e espaço após APK — atualização

A instalação de build-base, cmake, ninja, git, python3-dev, linux-headers, pkgconf e ca-certificates terminou sem erro. Saída final do APK: OK: 561.1 MiB in 107 packages. A instalação efetuou 33 ações (instalações e upgrades), incluindo Python 3.14.10-r1 para 3.14.10-r2.

Verificação posterior: GCC/G++ 15.2.0; CMake 4.2.3; Ninja 1.9; Git 2.54.1; Python 3.14.10; cabeçalhos disponíveis em /usr/include/python3.14. Filesystem raiz /dev/vda2: 579,3 MiB usados, 999,7 MiB livres (37% usados). A instalação das dependências de build está concluída; venv do runtime ainda não criado.

Próxima preparação: venv isolado em /opt/orn-runtime/venv; dependências Python do llama-cpp-python em wheels binários quando disponíveis; build temporário sob /var/tmp/orn-build, com TMPDIR apontando para esse diretório, sem cache do pip e sem paralelismo maior que 1.

### Observação sobre o relato Barrier / Amaranth

O usuário registrou que algo pareceu afetar Amaranth durante a sessão em que usa Barrier, mas não especificou o comportamento. A operação APK foi executada no guest Alpine por QemuDaemon.shell() e alterou somente pacotes dentro do guest. O screenshot enviado mostra o editor Lite XL com doxoade/tools/audio_systems/__init__.py; não mostra estado ou erro do Barrier. Possível lentidão momentânea de host/rede durante download e instalação não é evidência de alteração persistente no Barrier ou no outro computador. A relação causal fica indeterminada até obter o sintoma exato.



## Ajuste de segurança do baseline SIMD para o build

Na configuração CMake upstream de ggml, GGML_NATIVE=OFF, isoladamente, não garante que todas as opções SIMD fiquem desligadas: quando GGML_NATIVE_DEFAULT é ON no host, INS_ENB pode manter SSE4.2, AVX, AVX2, BMI2, FMA e F16C habilitados por default. Como o guest QEMU não anuncia SSE4.2, AVX, AVX2 ou BMI2, o build deve passar explicitamente:

- DGGML_NATIVE=OFF
- DGGML_SSE42=OFF
- DGGML_AVX=OFF
- DGGML_AVX2=OFF
- DGGML_BMI2=OFF
- DGGML_FMA=OFF
- DGGML_F16C=OFF
- DGGML_OPENMP=OFF
- DGGML_BLAS=OFF
- DGGML_CUDA=OFF

A notação acima corresponde aos argumentos CMake com o prefixo habitual "-D" (ex.: -DGGML_AVX=OFF). Isso evita que um baseline genérico dependa do CPUID virtual mais limitado.



## Venv e dependências Python — instalação concluída

No guest Alpine 3.24.4 foi criado o ambiente virtual /opt/orn-runtime/venv e /var/tmp/orn-build. O pip foi executado com TMPDIR=/var/tmp/orn-build, --no-cache-dir e --only-binary=:all:.

A instalação terminou com Successfully installed:
- scikit-build-core 1.1.2
- numpy 2.5.5 (wheel cp314 musllinux_1_2_x86_64, 17,1 MB)
- typing-extensions 4.16.0
- diskcache 5.6.3
- jinja2 3.1.6
- MarkupSafe 3.0.4 (wheel musllinux)
- packaging 26.4
- pathspec 1.1.1

Nenhuma dependência transitiva foi compilada. Ainda falta uma medição posterior de df -h / após essa instalação, além de validar imports, pip check e disponibilidade do backend CMake/Python. O build llama-cpp-python ainda não começou.



## Validação do venv e espaço posterior — 2026-11-24

O usuário executou pip check no ambiente /opt/orn-runtime/venv, que retornou No broken requirements found. Pacotes listados: diskcache 5.6.3, Jinja2 3.1.6, MarkupSafe 3.0.4, NumPy 2.5.5, packaging 26.4, pathspec 1.1.1, pip 26.2.2, scikit-build-core 1.1.2 e typing-extensions 4.16.0.

Depois da instalação do venv, /dev/vda2 passou a reportar 670,0 MiB usados, 909,0 MiB disponíveis (42% usado). O build llama-cpp-python ainda não começou.

A raiz de 2 GiB virtuais deixa menos de 1 GiB disponível. Antes de baixar/extrair/compilar o sdist (~79 MiB) e manter o build tree, instalar o wheel e copiar GGUF, recomenda-se expandir o disco para 4 GiB, aproveitando o backup verificado. Antes de qualquer resize, parar o daemon, confirmar nenhum processo QEMU ativo e fazer um segundo backup do estado atual, que inclui toolchain e venv.



## Geometria MBR do QCOW2 e utilitários de expansão — 2026-11-24

No Alpine 3.24.4, consulta read-only retornou:

- Disco /dev/vda: 2.147.483.648 bytes, 4.194.304 setores de 512 bytes (2 GiB).
- Tabela de partição MBR/DOS, conforme fdisk -l.
- /dev/vda1: início LBA 2048, 614.400 setores, fim LBA 616447, 300 MiB, tipo 83 Linux, bootável.
- /dev/vda2: início LBA 616448, 3.577.856 setores, fim LBA 4194303, aproximadamente 1.747 MiB, tipo 83 Linux, ext4 montado como raiz.
- UUID vda1: 4e11f7e4-67bc-4192-a412-6aba1020cb97.
- UUID vda2: 62f96db6-e0d1-4171-ad9d-2df3c696079a.
- e2fsck e blkid existem. sfdisk, parted, growpart, resize2fs e lsblk não estão no PATH.

A partição raiz começa em 616448; esse LBA deve ser mantido exatamente durante a expansão. O fim atual é o último setor do disco. A tabela não tem partição intermediária entre vda1 e vda2. Não apagar, formatar, mover, nem alterar o início da partição 2.

Alpine v3.24 oferece cloud-utils-growpart (subpacote de community) com growpart e dependências partx/sfdisk; e2fsprogs-extra fornece /usr/sbin/resize2fs. A simulação/instalação desses utilitários deve preceder o procedimento de resize. O procedimento proposto: segundo backup do estado atual com QEMU parado → qemu-img resize positivo 2 GiB→4 GiB → reboot → growpart /dev/vda 2 → confirmar tabela/start LBA → resize2fs /dev/vda2 → confirmar df -h /. O resize do filesystem ocorre somente depois de validar que a partição foi expandida.



## Simulação de ferramentas de crescimento de partição — T02

A verificação confirmou que /sbin/fdisk é link/applet pertencente a BusyBox 1.37.0-r31; não é o fdisk completo de util-linux. O conjunto simulado cloud-utils-growpart e e2fsprogs-extra resolveria seis pacotes:
- libsmartcols 2.42.3-r1
- partx 2.42.3-r1
- libfdisk 2.42.3-r1
- sfdisk 2.42.3-r1
- cloud-utils-growpart 0.33-r1
- e2fsprogs-extra 1.47.4-r0

Resultado de APK: OK: 562.2 MiB in 113 packages. A simulação não instalou os pacotes. Próximo passo: apk add --no-cache cloud-utils-growpart e2fsprogs-extra; depois verificar command -v growpart, sfdisk, resize2fs e espaço em /.



## Ferramentas de crescimento instaladas — T02

O usuário instalou cloud-utils-growpart e e2fsprogs-extra no Alpine 3.24.4. APK concluiu com OK: 562.2 MiB in 113 packages.

Verificação:
- growpart: /usr/bin/growpart
- sfdisk: /sbin/sfdisk, util-linux 2.42.3
- resize2fs: /usr/sbin/resize2fs

O fdisk anterior era o applet BusyBox 1.37.0-r31. A tabela real foi exportada por sfdisk -d:
label dos; label-id 0x0a4f7c3f
vda1 start 2048 size 614400 type 83 bootable
vda2 start 616448 size 3577856 type 83

Depois da instalação, a raiz reportou 671.2 MiB usados e 907.9 MiB disponíveis (43% ocupados). Nenhuma partição ou filesystem foi alterado. Próximo passo: parar daemon, confirmar ausência de processos QEMU, fazer backup idêntico e verificá-lo por SHA256; apenas depois redimensionar a imagem QCOW2 de 2 GiB para 4 GiB.
