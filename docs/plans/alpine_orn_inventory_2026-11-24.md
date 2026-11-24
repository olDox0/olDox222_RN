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
